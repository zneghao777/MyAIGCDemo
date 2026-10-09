from copy import deepcopy
import hashlib
import subprocess
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import Session
from app.core.errors import AppError
from app.models import Asset, Candidate, Project, Scene, Task
from app.providers import providers
from app.services import creative, video
from app.services.video_correction import MAX_BYTES, create_candidate
from app.tasks.execute import execute_job


@pytest_asyncio.fixture
async def clips(tmp_path):
    output = {}
    for duration in (6.58, 3):
        path = tmp_path / f"{duration}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x180:r=24",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(path),
            ],
            check=True,
        )
        output[duration] = path.read_bytes()
    return output


async def prepare(client, monkeypatch, raw, retake=False):
    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    monkeypatch.setattr(get_settings(), "video_points_hard_limit", 1000)
    provider = type(
        "Video",
        (),
        {
            "balance": AsyncMock(return_value={"available_points": 1000}),
            "create": AsyncMock(side_effect=["original-remote", "second-remote"]),
            "query": AsyncMock(
                return_value={
                    "status": "succeeded",
                    "fileUrl": "https://example.com/mock.mp4",
                    "resolution": "480P",
                    "usage": {"output_seconds": 6},
                }
            ),
        },
    )()
    monkeypatch.setattr(providers(), "video", provider)
    monkeypatch.setattr("app.tasks.execute.fetch_bytes", AsyncMock(return_value=raw))
    p = (
        await client.post(
            "/api/projects",
            json={
                "name": "修正来源测试",
                "ratio": "16:9",
                "scenes": [{"title": "暗灯", "imagePrompt": "灯仍熄灭", "durationSec": 6}],
            },
        )
    ).json()
    sid, pid = p["scenes"][0]["id"], p["id"]
    for kind in ("image", "video"):
        response = await client.post("/api/tasks", json={"projectId": pid, "sceneIds": [sid], "kind": kind})
        assert response.status_code == 202, response.text
        tid = response.json()["queued"][0]["id"]
        await execute_job(tid)
    async with Session() as db:
        scene, task, project = await db.get(Scene, sid), await db.get(Task, tid), await db.get(Project, pid)
        assert task.status == "done"
        old = {
            "key": scene.video_key,
            "asset_id": task.result["assetId"],
            "take": tid,
            "source": deepcopy(task.payload["video_source"]),
            "provider_task_id": task.provider_task_id,
            "model": task.payload["model"],
            "raw_output": task.result["providerOutput"],
            "materials": task.result["materials"],
            "post_processing": [],
            "accepted": False,
        }
        scene.creative = {"version": 1, "shot": {}, "video": old, "video_takes": [old]}
        await db.commit()
    if retake:
        async with Session() as db:
            scene = await db.get(Scene, sid)
            scene.video_prompt = "修改后的可见动作输入"
            await db.commit()
        response = await client.post(
            f"/api/scenes/{sid}/video-retake",
            json={"expected": 1, "reason": "模拟另一个已完成但不合格的take", "nonce": "correction-base-take"},
        )
        assert response.status_code == 202, response.text
        await execute_job(response.json()["id"])
    async with Session() as db:
        scene = await db.get(Scene, sid)
        project = await db.get(Project, pid)
        project.creative = {"version": 1, "locations": {}, "plan": None}
        state = deepcopy(scene.creative)
        state["review"] = {
            "status": "accepted",
            "checks": {"identity": True},
            "fingerprint": creative.review_fingerprint(scene),
        }
        scene.creative = state
        await db.commit()
        base = deepcopy(scene.creative["video"])
        expected = scene.creative["version"]
    return pid, sid, tid, old, base, expected, provider


async def upload(client, sid, tid, expected, raw, mime="video/mp4"):
    return await client.post(
        f"/api/creative/scenes/{sid}/video-correction",
        data={
            "expected": str(expected),
            "reason": "采用历史暗灯H3原片，校准已有配声，不再调用模型",
            "source_task_id": tid,
        },
        files={"file": ("corrected.mp4", raw, mime)},
    )


async def test_historical_h3_upload_select_preserves_real_provenance_without_new_task(
    client, monkeypatch, clips
):
    pid, sid, tid, old, base, expected, provider = await prepare(
        client, monkeypatch, clips[6.58], retake=True
    )
    async with Session() as db:
        scene = await db.get(Scene, sid)
        prior_render = creative.render_fingerprint([scene], "16:9", "电影写实")
        prior_static = creative.preview_fingerprint([scene])
        tasks_before = list((await db.scalars(select(Task).where(Task.project_id == pid))).all())
        assert creative.review_current(scene)
    response = await upload(client, sid, tid, expected, clips[6.58])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["modelCalled"] is False and 6.58 <= body["durationSeconds"] < 6.7
    repeated = await upload(client, sid, tid, expected, clips[6.58])
    assert repeated.json()["candidateId"] == body["candidateId"]
    async with Session() as db:
        scene = await db.get(Scene, sid)
        candidate = await db.get(Candidate, body["candidateId"])
        assert scene.video_key == base["key"] and scene.creative["version"] == expected
        assert candidate.kind == "video_correction" and candidate.task_id == tid
        assert candidate.data["source_video_key"] == old["key"]
        assert candidate.data["base_video_key"] == base["key"]
        assert candidate.data["original_source"] == old["source"]
        assert candidate.data["parent_trace"]["provider_task_id"] == "original-remote"
        assert (
            candidate.data["parent_task_snapshot"]["result"]["providerOutput"]["usage"]["output_seconds"] == 6
        )
        assert candidate.data["sha256"] == hashlib.sha256(clips[6.58]).hexdigest()
        assert candidate.data["post_processing"][-1]["adopted_historical_h3"] is True
    state = (await client.get(f"/api/creative/projects/{pid}")).json()
    assert next(c for c in state["candidates"] if c["id"] == body["candidateId"])["stale"] is False
    selected = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": body["candidateId"], "expected": expected},
    )
    assert selected.status_code == 200, selected.text
    async with Session() as db:
        scene = await db.get(Scene, sid)
        trace = scene.creative["video"]
        assert trace["key"] != base["key"] and scene.video_key == trace["key"]
        assert trace["parent_task_id"] == tid and trace["take"] == body["candidateId"]
        assert trace["original_source"] == old["source"]
        assert trace["source"] == await video.current_source(db, scene, "16:9")
        assert trace["source"] != trace["original_source"]
        assert not video.is_stale(scene, "16:9") and trace["accepted"] is False
        assert scene.creative["review"]["status"] == "pending" and scene.creative["review"]["checks"] == {}
        assert scene.creative["review_history"][-1]["status"] == "accepted" and not creative.review_current(
            scene
        )
        assert {old["key"], base["key"], trace["key"]} <= {t["key"] for t in scene.creative["video_takes"]}
        assert scene.order_index == 0 and scene.duration_sec == 6
        assert creative.render_fingerprint([scene], "16:9", "电影写实") != prior_render
        assert creative.preview_fingerprint([scene]) == prior_static
        assert len(list((await db.scalars(select(Task).where(Task.project_id == pid))).all())) == len(
            tasks_before
        )
    state = (await client.get(f"/api/creative/projects/{pid}")).json()
    candidate = next(c for c in state["candidates"] if c["id"] == body["candidateId"])
    assert candidate["selected"] is True and candidate["stale"] is False
    assert provider.create.await_count == 2
    assert all(k in providers().storage.objects for k in (old["key"], base["key"]))


@pytest.mark.parametrize("changed", ["input", "base"])
async def test_correction_selection_rejects_changed_input_or_base_take(client, monkeypatch, clips, changed):
    pid, sid, tid, old, _, expected, _ = await prepare(client, monkeypatch, clips[6.58])
    response = await upload(client, sid, tid, expected, clips[6.58])
    assert response.status_code == 200, response.text
    async with Session() as db:
        scene = await db.get(Scene, sid)
        state = deepcopy(scene.creative)
        state["version"] += 1
        if changed == "input":
            scene.video_prompt = "改变当前动作"
        else:
            scene.video_key = "new-base.mp4"
            state["video"]["key"] = scene.video_key
        scene.creative = state
        await db.commit()
    selected = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": response.json()["candidateId"], "expected": expected + 1},
    )
    assert selected.status_code == 409 and selected.json()["error"]["code"] == "STALE_CANDIDATE"
    async with Session() as db:
        scene = await db.get(Scene, sid)
        assert scene.video_key == (old["key"] if changed == "input" else "new-base.mp4")


async def test_correction_rejects_foreign_source_bad_duration_format_and_active_task(
    client, monkeypatch, clips
):
    pid, sid, tid, old, _, expected, _ = await prepare(client, monkeypatch, clips[6.58])
    _, sid2, _, _, _, expected2, _ = await prepare(client, monkeypatch, clips[6.58])
    foreign = await upload(client, sid2, tid, expected2, clips[6.58])
    assert foreign.status_code == 422 and foreign.json()["error"]["code"] == "INVALID_VIDEO_SOURCE"
    short = await upload(client, sid, tid, expected, clips[3])
    assert short.status_code == 422 and short.json()["error"]["code"] == "VIDEO_DURATION_MISMATCH"
    mime = await upload(client, sid, tid, expected, clips[6.58], "image/png")
    assert mime.status_code == 422 and mime.json()["error"]["code"] == "INVALID_MEDIA"
    corrupt = await upload(client, sid, tid, expected, b"\x00\x00\x00\x20ftypisomcorrupt")
    assert corrupt.status_code == 422 and corrupt.json()["error"]["code"] == "INVALID_MEDIA"
    stale_version = await upload(client, sid, tid, expected + 1, clips[6.58])
    assert stale_version.status_code == 409
    async with Session() as db:
        db.add(
            Task(
                project_id=pid,
                scene_id=sid,
                kind="video",
                status="queued",
                payload={},
                dedupe_key="active-mock",
            )
        )
        await db.commit()
    blocked = await upload(client, sid, tid, expected, clips[6.58])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "SCENE_HAS_RUNNING_TASK"
    async with Session() as db:
        assert not list(
            (await db.scalars(select(Candidate).where(Candidate.kind == "video_correction"))).all()
        )
        assert (await db.get(Scene, sid)).video_key == old["key"]


async def test_correction_size_is_rejected_before_saving_or_calling_a_provider():
    with pytest.raises(AppError) as error:
        await create_candidate(
            None,
            "scene",
            0,
            "修正",
            "task",
            b"\x00\x00\x00\x20ftyp" + b"x" * MAX_BYTES,
            "video/mp4",
            "large.mp4",
        )
    assert error.value.code == "PAYLOAD_TOO_LARGE"
