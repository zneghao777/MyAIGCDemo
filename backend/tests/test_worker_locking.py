"""Real PostgreSQL concurrency; fixture asserts and isolates the _test database."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.api.routers import creative as routes
from app.core.config import get_settings
from app.core.db import Session
from app.core.errors import AppError
from app.models import Project, Scene, Task
from app.providers import providers
from app.schemas.creative import Edit
from app.services import creative as flow
from app.services.locking import locked_scene
from app.services.resources import require
from app.tasks.execute import execute_job
from test_video_pipeline import prepare_video_jobs


async def seed_scene():
    async with Session() as db:
        p = Project(name="锁回归", creative={"version": 1})
        db.add(p)
        await db.flush()
        sc = Scene(project_id=p.id, order_index=0, creative={"version": 1, "shot": {"action": "原始动作"}})
        db.add(sc)
        await db.commit()
        return p.id, sc.id


async def test_cached_worker_waits_for_api_and_preserves_edit(env):
    pid, sid = await seed_scene()
    async with Session() as api_db, Session() as worker_db:
        cached = await require(worker_db, Scene, sid)
        assert cached.creative["version"] == 1
        await routes.project(api_db, pid)
        sc = await require(api_db, Scene, sid)
        await flow.save_state(api_db, sc, {**sc.creative, "shot": {"action": "API 修改"}}, "scene")
        worker = asyncio.create_task(locked_scene(worker_db, sid, check_idle=False))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(worker), .1)
        await api_db.commit()
        _, current = await asyncio.wait_for(worker, 3)
        assert current.creative["version"] == 2 and current.creative["shot"]["action"] == "API 修改"
        await flow.save_state(worker_db, current, {**current.creative, "video": {"key": "result"}}, "scene")
        await worker_db.commit()
    async with Session() as db:
        sc = await require(db, Scene, sid)
        assert sc.creative["version"] == 3
        assert sc.creative["shot"]["action"] == "API 修改"
        assert sc.creative["video"]["key"] == "result"


async def test_api_waiting_for_worker_rejects_stale_expected(env):
    _, sid = await seed_scene()
    async with Session() as api_db, Session() as worker_db:
        await require(api_db, Scene, sid)  # Populate before worker obtains its lock.
        _, sc = await locked_scene(worker_db, sid, check_idle=False)
        await flow.save_state(worker_db, sc, {**sc.creative, "video": {"key": "current"}}, "scene")
        api_write = asyncio.create_task(routes.edit_scene(sid, Edit(expected=1, data={}), api_db))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(api_write), .1)
        await worker_db.commit()
        with pytest.raises(AppError) as error:
            await asyncio.wait_for(api_write, 3)
        assert error.value.code == "STALE_VERSION"
        await api_db.rollback()
    async with Session() as db:
        sc = await require(db, Scene, sid)
        assert sc.creative["version"] == 2 and sc.creative["video"]["key"] == "current"


async def test_actual_video_worker_retains_concurrent_api_review(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    monkeypatch.setattr(get_settings(), "video_points_hard_limit", 1000)
    generating, release = asyncio.Event(), asyncio.Event()
    async def query(_):
        generating.set()
        await asyncio.wait_for(release.wait(), 3)
        return {"status": "succeeded", "fileUrl": "https://example.com/video.mp4"}
    provider = type("Video", (), {"balance": AsyncMock(return_value={"available_points": 1000}), "create": AsyncMock(return_value="worker-remote"), "query": staticmethod(query)})()
    monkeypatch.setattr(providers(), "video", provider)
    monkeypatch.setattr("app.tasks.execute.fetch_bytes", AsyncMock(return_value=b"video"))
    p, jobs = await prepare_video_jobs(client, 1)
    sid = p["scenes"][0]["id"]
    async with Session() as db:
        sc = await require(db, Scene, sid)
        sc.creative = {"version": 1, "shot": {}}
        await db.commit()
    worker = asyncio.create_task(execute_job(jobs[0]["id"]))
    await asyncio.wait_for(generating.wait(), 3)
    response = await client.post(f"/api/creative/scenes/{sid}/review", json={"expected": 1, "data": {"status": "pending", "notes": "API 留下的审阅意见"}})
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    release.set()
    await asyncio.wait_for(worker, 5)
    async with Session() as db:
        task = await require(db, Task, jobs[0]["id"])
        sc = await require(db, Scene, sid)
        assert task.status == "done", task.error
        assert sc.creative["version"] == 3
        assert sc.creative["review"]["notes"] == "API 留下的审阅意见"
        assert sc.creative["video"]["key"] == sc.video_key
