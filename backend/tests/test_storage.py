import io
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit

import pytest
from botocore.exceptions import ClientError
from PIL import Image
from pydantic import SecretStr

from app.core.errors import AppError
from app.core.config import get_settings
from app.providers import providers
from app.providers.local import LocalStorage
from app.providers.qiniu import QiniuTemporaryMedia
from app.tasks.execute import execute_job
from test_backend import create, enqueue


async def test_local_roundtrip_and_path_containment(tmp_path):
    storage = LocalStorage(tmp_path / "media", "http://test/media")
    await storage.health()
    key = "projects/one/中文.png"
    url = await storage.put(key, b"image", "image/png")
    assert url == "http://test/media/projects/one/%E4%B8%AD%E6%96%87.png"
    assert await storage.get(key) == b"image"
    assert storage.path(key).read_bytes() == b"image"
    assert not list(storage.root.rglob(".upload-*"))
    outside = tmp_path / "private"
    outside.mkdir()
    (storage.root / "escape").symlink_to(outside, target_is_directory=True)
    for unsafe in ("../private/key", "/etc/passwd", "projects/../../key", "escape/key", "a\\b", "a//b"):
        with pytest.raises(AppError):
            await storage.put(unsafe, b"bad", "image/png")
    await storage.delete(key)
    await storage.delete(key)
    with pytest.raises(AppError) as err:
        await storage.get(key)
    assert err.value.code == "ASSET_NOT_FOUND"


async def test_local_playback_range_cache_and_missing(client, monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path, "http://test/media")
    monkeypatch.setattr(providers(), "storage", storage)
    await storage.put("projects/p/movie.mp4", b"0123456789", "video/mp4")
    url = storage.url("projects/p/movie.mp4")
    response = await client.get(url)
    assert response.status_code == 200 and response.content == b"0123456789"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert "immutable" in response.headers["cache-control"]
    head = await client.head(url)
    assert head.status_code == 200 and head.content == b"" and head.headers["content-length"] == "10"
    cached = await client.get(url, headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    segment = await client.get(url, headers={"Range": "bytes=2-5"})
    assert segment.status_code == 206 and segment.content == b"2345"
    assert segment.headers["content-range"] == "bytes 2-5/10"
    assert (await client.get(url, headers={"Range": "bytes=20-30"})).status_code == 416
    assert (await client.get("/media/projects/p/missing.mp4")).status_code == 404
    assert (await client.get("/media/%2e%2e/.env.local")).status_code in (404, 422)
    await storage.put(".private", b"hidden", "text/plain")
    assert (await client.get("/media/.private")).status_code == 404
    providers().external_media.publish.assert_not_awaited()


async def test_local_upload_binding_copy_and_health_without_qiniu(client, monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path, "http://test/media")
    monkeypatch.setattr(providers(), "storage", storage)
    monkeypatch.setattr(get_settings(), "qiniu_access_key", SecretStr(""))
    monkeypatch.setattr(get_settings(), "qiniu_secret_key", SecretStr(""))
    p = await create(client, 0)
    out = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(out, format="PNG")
    response = await client.post(
        "/api/assets/upload",
        data={"projectId": p["id"]},
        files={"file": ("ref.png", out.getvalue(), "image/png")},
    )
    assert response.status_code == 201
    asset = response.json()
    assert asset["url"].startswith("http://test/media/")
    assert (await client.get(asset["url"])).content == out.getvalue()
    character = await client.post(
        f"/api/projects/{p['id']}/characters", json={"name": "阿信", "image": asset["url"]}
    )
    assert character.status_code == 201
    copy = await client.post(f"/api/projects/{p['id']}/copy")
    assert copy.status_code == 201
    copied_url = copy.json()["characters"][0]["image"]
    assert copied_url != asset["url"]
    assert (await client.get(copied_url)).content == out.getvalue()
    foreign = await client.post(
        f"/api/projects/{copy.json()['id']}/characters", json={"name": "foreign", "image": asset["url"]}
    )
    assert foreign.status_code == 422
    await storage.delete(asset["objectKey"])
    assert (await client.get(copied_url)).status_code == 200
    health = await client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["checks"]["local_media"] == "ok" and "cos" not in health.json()["checks"]
    providers().external_media.publish.assert_not_awaited()


def bridge_with_client():
    bridge = QiniuTemporaryMedia()
    bridge.client = Mock()
    bridge.client.generate_presigned_url.return_value = "https://external.example/signed"
    return bridge


async def test_external_upload_reuses_today_and_signs_get():
    bridge = bridge_with_client()
    missing = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject"
    )
    bridge.client.head_object.side_effect = [missing, {}]
    assert await bridge.publish(b"reference", "image/png") == "https://external.example/signed"
    await bridge.publish(b"reference", "image/png")
    bridge.client.put_object.assert_called_once()
    upload = bridge.client.put_object.call_args.kwargs
    assert upload["Body"] == b"reference"
    assert upload["Key"].startswith(
        bridge.s.qiniu_temp_prefix + datetime.now(timezone.utc).strftime("%Y%m%d") + "/"
    )
    assert bridge.client.generate_presigned_url.call_args.args == ("get_object",)
    assert bridge.client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 86400


async def test_external_permission_failure_does_not_upload_or_leak():
    bridge = bridge_with_client()
    bridge.client.head_object.side_effect = ClientError(
        {
            "Error": {"Code": "AccessDenied", "Message": "secret-detail"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "HeadObject",
    )
    with pytest.raises(AppError) as err:
        await bridge.publish(b"reference", "image/png")
    assert "secret-detail" not in err.value.message
    bridge.client.put_object.assert_not_called()


async def test_cleanup_only_expired_temporary_objects():
    bridge = bridge_with_client()
    now = datetime.now(timezone.utc)
    prefix = bridge.s.qiniu_temp_prefix
    bridge.client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {"Key": prefix + "old", "LastModified": now - timedelta(days=4)},
                {"Key": prefix + "recent", "LastModified": now - timedelta(days=2)},
                {"Key": "unrelated/old", "LastModified": now - timedelta(days=4)},
            ]
        }
    ]
    assert await bridge.cleanup() == 1
    bridge.client.delete_object.assert_called_once_with(Bucket=bridge.s.qiniu_s3_bucket, Key=prefix + "old")
    bridge.client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket=bridge.s.qiniu_s3_bucket, Prefix=prefix
    )


async def test_lifecycle_preserves_other_rules():
    bridge = bridge_with_client()
    other = {"ID": "OtherRule", "Status": "Enabled", "Prefix": "other/", "Expiration": {"Days": 30}}
    bridge.client.get_bucket_lifecycle_configuration.return_value = {"Rules": [other]}
    await bridge.configure_lifecycle()
    rules = bridge.client.put_bucket_lifecycle_configuration.call_args.kwargs["LifecycleConfiguration"][
        "Rules"
    ]
    assert rules[0] == other
    assert rules[1]["Expiration"] == {"Days": 3}
    assert rules[1]["Filter"] == {"Prefix": bridge.s.qiniu_temp_prefix}


async def test_video_uses_inline_reference_and_saves_result_locally(client, monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path, "http://test/media")
    monkeypatch.setattr(providers(), "storage", storage)
    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    p = await create(client, 1)
    image_task = (await enqueue(client, p))[0]
    await execute_job(image_task["id"])
    providers().external_media.publish.assert_not_awaited()
    video = Mock(
        balance=AsyncMock(return_value={"available_points": 1000}),
        create=AsyncMock(return_value="external-job"),
        query=AsyncMock(return_value={"status": "success", "fileUrl": "https://provider.example/movie.mp4"}),
    )
    monkeypatch.setattr(providers(), "video", video)
    monkeypatch.setattr("app.tasks.execute.fetch_bytes", AsyncMock(return_value=b"video-result"))
    video_task = (await enqueue(client, p, "video"))[0]
    await execute_job(video_task["id"])
    providers().external_media.publish.assert_not_awaited()
    assert video.create.call_args.args[1].startswith("data:image/png;base64,")
    updated = (await client.get(f"/api/projects/{p['id']}")).json()
    url = updated["scenes"][0]["videoUrl"]
    assert url.startswith("http://test/media/")
    assert (await client.get(urlsplit(url).path)).content == b"video-result"


async def test_local_ffmpeg_export_and_project_cleanup(client, monkeypatch, tmp_path):
    import json
    import subprocess

    from sqlalchemy import select
    from app.core.db import Session
    from app.models import Scene, Asset
    from app.services.resources import save_asset
    from app.tasks.execute import cleanup
    import asyncio

    storage = LocalStorage(tmp_path / "media", "http://test/media")
    monkeypatch.setattr(providers(), "storage", storage)
    p = await create(client, 1)
    for task in await enqueue(client, p):
        await execute_job(task["id"])
    async with Session() as db:
        scene = await db.get(Scene, p["scenes"][0]["id"])
        raw = await providers().tts.synthesize(scene.dialogue, "test-voice")
        audio = await save_asset(db, p["id"], "audio", raw, "audio/mpeg", "mp3", duration_ms=600)
        scene.audio_key = audio.object_key
        await db.commit()
    response = await client.post(
        f"/api/projects/{p['id']}/exports", json={"resolution": "720p", "fps": 24, "subtitles": True}
    )
    assert response.status_code == 202
    await execute_job(response.json()["taskId"])
    task = (await client.get("/api/tasks/" + response.json()["taskId"])).json()
    assert task["status"] == "done", task
    export = (await client.get("/api/exports/" + response.json()["exportJobId"])).json()
    key = urlsplit(export["url"]).path.removeprefix("/media/")
    meta = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(storage.path(key))]
        )
    )
    assert {stream["codec_type"] for stream in meta["streams"]} == {"video", "audio"}
    assert (await client.get(export["url"], headers={"Range": "bytes=0-99"})).status_code == 206
    assert (await client.get(export["subtitleUrl"])).status_code == 200
    assert (await client.get(export["coverUrl"])).status_code == 200
    providers().external_media.publish.assert_not_awaited()
    async with Session() as db:
        keys = list((await db.scalars(select(Asset.object_key).where(Asset.project_id == p["id"]))).all())
    assert (await client.delete(f"/api/projects/{p['id']}")).status_code == 204
    await asyncio.to_thread(cleanup.run)
    assert all(not storage.path(key).exists() for key in keys)
