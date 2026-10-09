import asyncio
import io
import json
import subprocess
from PIL import Image
from app.core.config import get_settings
from app.tasks.execute import execute_job
from app.providers import providers


async def create(client, n=2):
    r = await client.post(
        "/api/projects",
        json={
            "name": "末世信使",
            "ratio": "16:9",
            "scenes": [
                {
                    "title": f"镜{i}",
                    "durationSec": 4,
                    "imagePrompt": "机器人",
                    "dialogue": "这封信，一定会送到。",
                }
                for i in range(n)
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def enqueue(client, p, kind="image"):
    r = await client.post(
        "/api/tasks", json={"projectId": p["id"], "sceneIds": [s["id"] for s in p["scenes"]], "kind": kind}
    )
    assert r.status_code == 202, r.text
    return r.json()["queued"]


async def test_crud_order_copy_ownership(client):
    p = await create(client)
    ids = [s["id"] for s in p["scenes"]]
    assert (await client.patch(f"/api/scenes/{ids[0]}", json={"durationSec": 1})).status_code == 422
    assert (
        await client.patch(f"/api/projects/{p['id']}/scenes/order", json={"ids": list(reversed(ids))})
    ).status_code == 200
    assert (
        await client.patch(f"/api/projects/{p['id']}/scenes/order", json={"ids": [ids[0], ids[0]]})
    ).status_code == 422
    copy = await client.post(f"/api/scenes/{ids[0]}/copy")
    assert copy.status_code == 201, copy.text
    assert (await client.delete(f"/api/scenes/{ids[1]}")).status_code == 204
    updated = (await client.get(f"/api/projects/{p['id']}")).json()
    assert [s["orderIndex"] for s in updated["scenes"]] == [0, 1]
    c = await client.post(f"/api/projects/{p['id']}/characters", json={"name": "阿信"})
    assert c.status_code == 201, c.text
    edit = await client.patch(
        "/api/characters/" + c.json()["id"], json={"voiceId": "test-voice", "voice": "男声 · 青年"}
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["voiceId"] == "test-voice"
    other = await create(client, 1)
    invalid = await client.post(
        "/api/tasks", json={"projectId": p["id"], "sceneIds": [other["scenes"][0]["id"]], "kind": "image"}
    )
    assert invalid.json()["rejected"][0]["code"] == "RESOURCE_NOT_FOUND"
    assert (
        await client.post("/api/tasks", json={"projectId": p["id"], "sceneIds": ids, "kind": "video"})
    ).status_code == 403


async def test_duplicate_budget_cancel_retry(client):
    p = await create(client, 1)
    s = get_settings()
    prices = s.cost_unit_price_json
    limit = s.cost_hard_limit_cents
    s.cost_unit_price_json = {"imagePerCall": 60}
    s.cost_hard_limit_cents = 100
    try:
        tasks = await enqueue(client, p)
        duplicate = await client.post(
            "/api/tasks", json={"projectId": p["id"], "sceneIds": [p["scenes"][0]["id"]], "kind": "image"}
        )
        assert duplicate.json()["rejected"][0]["code"] == "SCENE_HAS_RUNNING_TASK"
        assert (
            await client.patch("/api/scenes/" + p["scenes"][0]["id"], json={"title": "不允许"})
        ).status_code == 409
        await client.post("/api/tasks/" + tasks[0]["id"] + "/cancel")
        await execute_job(tasks[0]["id"])
        assert (await client.get("/api/tasks/" + tasks[0]["id"])).json()["status"] == "cancelled"
        retry = await client.post("/api/tasks/" + tasks[0]["id"] + "/retry")
        assert retry.status_code == 202, retry.text
        assert retry.json()["id"] != tasks[0]["id"]
        await execute_job(retry.json()["id"])
        task = (await client.get("/api/tasks/" + retry.json()["id"])).json()
        assert task["status"] == "done", task
        assert task["costCents"] == 60
        await client.patch("/api/scenes/" + p["scenes"][0]["id"], json={"imagePrompt": "换个画面"})
        r = await client.post(
            "/api/tasks", json={"projectId": p["id"], "sceneIds": [p["scenes"][0]["id"]], "kind": "image"}
        )
        assert r.status_code == 402, r.text
    finally:
        s.cost_unit_price_json = prices
        s.cost_hard_limit_cents = limit


async def test_script_and_assistance(client):
    p = await create(client, 0)
    r = await client.post(
        f"/api/projects/{p['id']}/script/generate",
        json={"idea": "机器人学会了说谎", "sceneCount": 8, "durationSec": 32},
    )
    assert r.status_code == 202, r.text
    await execute_job(r.json()["taskId"])
    p = (await client.get("/api/projects/" + p["id"])).json()
    assert len(p["scenes"]) == 8
    r = await client.post(
        "/api/ai/optimize-prompt", json={"projectId": p["id"], "sceneId": p["scenes"][0]["id"]}
    )
    await execute_job(r.json()["taskId"])
    assert (await client.get("/api/tasks/" + r.json()["taskId"])).json()["result"]["text"] == "清晰的电影构图"


async def test_upload_copy_delete(client, env):
    p = await create(client, 1)
    raw = io.BytesIO()
    Image.new("RGB", (64, 64)).save(raw, format="PNG")
    r = await client.post(
        "/api/assets/upload",
        data={"projectId": p["id"]},
        files={"file": ("a.png", raw.getvalue(), "image/png")},
    )
    assert r.status_code == 201, r.text
    bad = await client.post(
        "/api/assets/upload",
        data={"projectId": p["id"]},
        files={"file": ("a.png", b"not-image", "image/png")},
    )
    assert bad.status_code == 422
    c = await client.post(
        f"/api/projects/{p['id']}/characters", json={"name": "阿信", "image": r.json()["url"]}
    )
    assert c.status_code == 201, c.text
    copy = await client.post(f"/api/projects/{p['id']}/copy")
    assert copy.status_code == 201, copy.text
    assert copy.json()["characters"][0]["image"] != c.json()["image"]
    assert (await client.delete(f"/api/projects/{p['id']}")).status_code == 204
    assert (await client.get("/api/projects/" + copy.json()["id"])).status_code == 200


async def test_pause_and_cancel_during_provider(client, monkeypatch):
    p = await create(client, 1)
    tasks = await enqueue(client, p)
    id = tasks[0]["id"]
    await client.post(f"/api/projects/{p['id']}/queue/pause", json={"paused": True})
    await execute_job(id)
    assert (await client.get("/api/tasks/" + id)).json()["status"] == "queued"
    await client.post(f"/api/projects/{p['id']}/queue/pause", json={"paused": False})
    entered = asyncio.Event()
    release = asyncio.Event()
    original = providers().image.generate

    async def slow(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    monkeypatch.setattr(providers().image, "generate", slow)
    running = asyncio.create_task(execute_job(id))
    await asyncio.wait_for(entered.wait(), 10)
    await client.post("/api/tasks/" + id + "/cancel")
    release.set()
    await running
    assert (await client.get("/api/tasks/" + id)).json()["status"] == "cancelled"
    assert not (await client.get("/api/projects/" + p["id"])).json()["scenes"][0]["image"]


async def test_compose_real_mp4(client, env, tmp_path):
    p = await create(client, 8)
    for task in await enqueue(client, p):
        await execute_job(task["id"])
    # Simulate legacy media already saved before this upgrade; no speaker guessing.
    from app.core.db import Session
    from app.models import Scene
    from app.services.resources import save_asset
    async with Session() as db:
        for spec in p["scenes"]:
            sc = await db.get(Scene, spec["id"])
            raw = await providers().tts.synthesize(sc.dialogue, "explicit-legacy-voice")
            asset = await save_asset(db, p["id"], "audio", raw, "audio/mpeg", "mp3", duration_ms=600)
            sc.audio_key = asset.object_key
        await db.commit()
    r = await client.post(
        f"/api/projects/{p['id']}/exports", json={"resolution": "1080p", "fps": 24, "subtitles": True}
    )
    assert r.status_code == 202, r.text
    await execute_job(r.json()["taskId"])
    task = (await client.get("/api/tasks/" + r.json()["taskId"])).json()
    assert task["status"] == "done", task
    export = (await client.get("/api/exports/" + r.json()["exportJobId"])).json()
    key = export["url"].replace("https://media.example/", "")
    path = tmp_path / "output.mp4"
    path.write_bytes(env.objects[key])
    meta = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
        )
    )
    assert float(meta["format"]["duration"]) >= 30
    assert {s["codec_type"] for s in meta["streams"]} == {"video", "audio"}
    assert meta["streams"][0]["width"] == 1920 and meta["streams"][0]["height"] == 1080
    assert export["subtitleUrl"]
    history = (await client.get("/api/projects/" + p["id"] + "/exports")).json()
    assert history[0]["id"] == export["id"] and history[0]["url"] == export["url"]
    from pathlib import Path

    target = Path("../output/backend-verification")
    target.mkdir(parents=True, exist_ok=True)
    (target / "fake-provider-real-ffmpeg.mp4").write_bytes(path.read_bytes())


async def test_real_celery_redis_delivery(client):
    from celery.contrib.testing.worker import start_worker
    from app.worker import celery
    from app.services.jobs import dispatch_pending

    p = await create(client, 0)
    response = await client.post(
        f"/api/projects/{p['id']}/script/generate",
        json={"idea": "机器人", "sceneCount": 8, "durationSec": 32},
    )
    task_id = response.json()["taskId"]
    worker = start_worker(
        celery,
        pool="solo",
        concurrency=1,
        queues=["cineai.script"],
        perform_ping_check=False,
        shutdown_timeout=15,
    )
    await asyncio.to_thread(worker.__enter__)
    try:
        await dispatch_pending()
        for _ in range(100):
            task = (await client.get("/api/tasks/" + task_id)).json()
            if task["status"] in ("done", "failed"):
                break
            await asyncio.sleep(0.1)
        assert task["status"] == "done", task
    finally:
        await asyncio.to_thread(worker.__exit__, None, None, None)


async def test_sse_limit_and_cleanup(client):
    from app.api.routers.events import stream_response
    from app.core.events import publish, redis_client
    from app.core.errors import AppError
    from unittest.mock import AsyncMock
    import pytest

    p = await create(client, 0)
    request = AsyncMock()
    request.is_disconnected.return_value = False
    streams = [await stream_response(p["id"], request) for _ in range(5)]
    with pytest.raises(AppError) as exc:
        await stream_response(p["id"], request)
    assert exc.value.status == 429
    for stream in streams:
        first = await anext(stream.body_iterator)
        assert "connected" in first
    await publish(p["id"], "task", {"id": "test", "status": "running", "progress": 10})
    event = await asyncio.wait_for(anext(streams[0].body_iterator), 3)
    assert "event: task" in event
    for stream in streams:
        await stream.body_iterator.aclose()
    async with redis_client() as redis:
        assert await redis.zcard("cineai:sse:" + p["id"]) == 0
