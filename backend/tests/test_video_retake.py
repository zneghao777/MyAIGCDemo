import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import Session
from app.models import Scene, Task
from app.providers import providers
from app.tasks.execute import execute_job
from test_video_pipeline import prepare_video_jobs


async def original_take(client, monkeypatch, clear_selection=False):
    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    monkeypatch.setattr(get_settings(), "video_points_hard_limit", 1000)
    provider = type(
        "Video",
        (),
        {
            "balance": AsyncMock(return_value={"available_points": 1000}),
            "create": AsyncMock(side_effect=["original-remote", "retake-remote"]),
            "query": AsyncMock(
                return_value={"status": "succeeded", "fileUrl": "https://example.com/video.mp4"}
            ),
        },
    )()
    monkeypatch.setattr(providers(), "video", provider)
    monkeypatch.setattr("app.tasks.execute.fetch_bytes", AsyncMock(return_value=b"mock-video"))
    project, jobs = await prepare_video_jobs(client, 1)
    await execute_job(jobs[0]["id"])
    sid = project["scenes"][0]["id"]
    async with Session() as db:
        scene = await db.get(Scene, sid)
        original = await db.get(Task, jobs[0]["id"])
        assert original.status == "done"
        trace = {
            "key": scene.video_key,
            "asset_id": original.result["assetId"],
            "source": original.payload["video_source"],
            "take": original.id,
        }
        # Test data represents a paid take retained after a creative input edit.
        scene.creative = {"version": 1, "shot": {}, "video": trace, "video_takes": [trace]}
        if clear_selection:
            scene.video_key = None
        await db.commit()
    return project, sid, trace, provider


async def test_retake_dedupes_concurrent_clicks_and_preserves_old_take_until_success(client, monkeypatch):
    project, sid, old, provider = await original_take(client, monkeypatch, clear_selection=True)
    quote = (await client.get(f"/api/scenes/{sid}/video-quote")).json()
    assert quote["expected"] == 1 and quote["points"] == 25
    assert quote["projectPointsUsed"] == 25 and quote["reservedPoints"] == 0
    assert quote["previousVideoUrl"].endswith(old["key"])
    body = {"expected": 1, "reason": "让接线动作明确完成", "nonce": "stable-retake-one"}
    first, duplicate = await asyncio.gather(
        client.post(f"/api/scenes/{sid}/video-retake", json=body),
        client.post(f"/api/scenes/{sid}/video-retake", json=body),
    )
    assert first.status_code == duplicate.status_code == 202
    assert first.json()["id"] == duplicate.json()["id"]
    assert {first.json()["deduplicated"], duplicate.json()["deduplicated"]} == {False, True}
    tid = first.json()["id"]
    async with Session() as db:
        scene = await db.get(Scene, sid)
        task = await db.get(Task, tid)
        assert scene.video_key is None
        assert scene.creative["video"] == old and scene.creative["video_takes"] == [old]
        assert task.payload["retake"]["previous_video_key"] == old["key"]
        assert task.payload["submission_id"].startswith("retake-")
    active = (await client.get(f"/api/scenes/{sid}/video-quote")).json()
    assert active["projectPointsUsed"] == 50 and active["reservedPoints"] == 25
    assert len(active["activeTasks"]) == 1
    blocked = await client.post(
        f"/api/scenes/{sid}/video-retake", json={**body, "nonce": "another-retake-one"}
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "SCENE_HAS_RUNNING_TASK"
    await execute_job(tid)
    async with Session() as db:
        scene = await db.get(Scene, sid)
        task = await db.get(Task, tid)
        assert task.status == "done"
        assert scene.video_key != old["key"]
        assert [x["key"] for x in scene.creative["video_takes"]] == [old["key"], scene.video_key]
        assert scene.creative["video"]["retake"]["reason"] == body["reason"]
        assert scene.order_index == 0
        assert old["key"] in providers().storage.objects
    repeated = await client.post(f"/api/scenes/{sid}/video-retake", json=body)
    assert repeated.status_code == 202 and repeated.json()["id"] == tid
    assert repeated.json()["deduplicated"] is True
    assert provider.create.await_count == 2
    assert (
        provider.create.await_args_list[0].kwargs["idempotency_key"]
        != provider.create.await_args_list[1].kwargs["idempotency_key"]
    )
    stale = await client.post(f"/api/scenes/{sid}/video-retake", json={**body, "nonce": "another-retake-two"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_VERSION"
    all_jobs = (await client.get(f"/api/projects/{project['id']}/tasks")).json()
    assert len([x for x in all_jobs if x["kind"] == "video"]) == 2


async def test_failed_retake_keeps_existing_video_and_history(client, monkeypatch):
    _, sid, old, provider = await original_take(client, monkeypatch)
    provider.query.return_value = {"status": "failed"}
    body = {"expected": 1, "reason": "修正嘴部开合时间", "nonce": "stable-failed-retake"}
    created = await client.post(f"/api/scenes/{sid}/video-retake", json=body)
    assert created.status_code == 202
    await execute_job(created.json()["id"])
    async with Session() as db:
        scene = await db.get(Scene, sid)
        task = await db.get(Task, created.json()["id"])
        assert task.status == "failed"
        assert scene.video_key == old["key"]
        assert scene.creative["video"] == old and scene.creative["video_takes"] == [old]
    quote = (await client.get(f"/api/scenes/{sid}/video-quote")).json()
    assert quote["projectPointsUsed"] == 50 and quote["reservedPoints"] == 0
    # Recovery retains the original remote task, nonce and paid reservation.
    retry = await client.post(f"/api/tasks/{created.json()['id']}/retry")
    assert retry.status_code == 202
    duplicate = await client.post(f"/api/scenes/{sid}/video-retake", json=body)
    assert duplicate.json()["id"] == retry.json()["id"]
    provider.query.return_value = {"status": "succeeded", "fileUrl": "https://example.com/recovered.mp4"}
    await execute_job(retry.json()["id"])
    assert provider.create.await_count == 2
    assert provider.query.await_args.args == ("retake-remote",)
    recovered = (await client.get(f"/api/scenes/{sid}/video-quote")).json()
    assert recovered["projectPointsUsed"] == 50


async def test_retake_budget_counts_original_paid_take_and_rolls_back(client, monkeypatch):
    project, sid, old, _ = await original_take(client, monkeypatch)
    monkeypatch.setattr(get_settings(), "video_points_hard_limit", 49)
    created = await client.post(
        f"/api/scenes/{sid}/video-retake",
        json={"expected": 1, "reason": "修正灯光保持熄灭", "nonce": "stable-budget-retake"},
    )
    assert created.status_code == 402
    assert created.json()["error"]["code"] == "VIDEO_POINTS_LIMIT"
    async with Session() as db:
        scene = await db.get(Scene, sid)
        videos = list(
            (
                await db.scalars(select(Task).where(Task.project_id == project["id"], Task.kind == "video"))
            ).all()
        )
        assert len(videos) == 1
        assert scene.video_key == old["key"]
        assert deepcopy(scene.creative["video_takes"]) == [old]
