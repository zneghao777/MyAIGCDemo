"""Retry must reconstruct the same confirmed view/frame generation input."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks

from app.api.routers import jobs
from app.models import Task
from app.services import creative


@pytest.mark.parametrize(
    "operation,args",
    [
        ("character_image", {"view": "back"}),
        ("shot_image", {"frame": "last"}),
    ],
)
async def test_creative_retry_keeps_selected_view_or_last_frame(monkeypatch, operation, args):
    expected = {"operation": operation, "view": args.get("view", ""), "frame": args.get("frame", "first")}
    row = SimpleNamespace(
        status="failed",
        project_id="project",
        scene_id=None,
        kind="image",
        payload={
            "creative": {"operation": operation, "target": "target", "request": args, "input": expected}
        },
    )
    project = SimpleNamespace(id="project")
    new = SimpleNamespace(id="new-task")

    async def require(db, model, id, lock=False):
        return row if model is Task else project

    async def current_input(
        db, p, operation, target="", variant="", voice_id="", text="", view="", frame="first"
    ):
        return {"operation": operation, "view": view, "frame": frame}

    monkeypatch.setattr(jobs, "require", require)
    monkeypatch.setattr(jobs, "ensure_idle", AsyncMock())
    monkeypatch.setattr(creative, "current_input", current_input)
    created = AsyncMock(return_value=new)
    monkeypatch.setattr(jobs, "create_job", created)
    monkeypatch.setattr(jobs, "finish_submit", AsyncMock())
    monkeypatch.setattr(jobs, "task_out", lambda task: {"id": task.id})
    result = await jobs.retry("old-task", SimpleNamespace(), BackgroundTasks())
    assert result == {"id": "new-task"}
    assert created.call_args.args[3] == row.payload
