"""A tail is an edit of its selected shot frame, with a traceable dependency."""

import base64
import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from test_creative import fetch, generate, select, setup

from app.core.db import Session
from app.core.errors import AppError
from app.models import Project, Scene
from app.providers import providers
from app.services.video import validate_derived_tail


async def test_tail_requires_current_first_frame_and_references_only_that_frame(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    denied = await client.post(
        f"/api/creative/projects/{pid}/generate",
        json={"operation": "shot_image", "target": sid, "frame": "last"},
    )
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "FIRST_FRAME_REQUIRED"
    buffer = io.BytesIO()
    Image.new("RGB", (384, 256), "#d32e45").save(buffer, format="PNG")
    source = buffer.getvalue()
    uploaded = await client.post(
        f"/api/creative/scenes/{sid}/reference",
        json={
            "expected": p["scenes"][0]["creative"]["version"],
            "data": {"image": "data:image/png;base64," + base64.b64encode(source).decode()},
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    p = await select(client, pid, {"result": {"candidateId": uploaded.json()["candidateId"]}})
    first = p["scenes"][0]["creative"]["image"]
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    task = await generate(client, pid, "shot_image", target=sid, frame="last")
    assert spy.call_args.args[3] == [source]
    assert "相同景别" in spy.call_args.args[0] and "手部与按钮特写" in spy.call_args.args[0]
    p = await select(client, pid, task)
    tail = p["scenes"][0]["creative"]["last_frame"]
    assert tail["first_frame_reference"]["candidate_id"] == first["candidate_id"]
    assert tail["first_frame_reference"]["key"] == first["key"]
    assert tail["reference_count"] == 1 and tail["reference_mode"] == "shot-first-frame"
    async with Session() as db:
        project = await db.get(Project, pid)
        scene = await db.get(Scene, sid)
        await validate_derived_tail(db, project, scene, {"key": first["key"]}, tail["asset_id"])
        with pytest.raises(AppError) as mismatch:
            await validate_derived_tail(
                db, project, scene, {"key": "different-explicit-first"}, tail["asset_id"]
            )
        assert mismatch.value.code == "LAST_FRAME_STALE"
    again = await client.post(
        f"/api/creative/projects/{pid}/generate",
        json={"operation": "shot_image", "target": sid, "frame": "last"},
    )
    assert again.status_code == 202 and again.json()["taskId"] == task["id"]
    await select(client, pid, await generate(client, pid, "shot_image", target=sid, nonce="new-first"))
    state = await fetch(client, pid)
    original = next(c for c in state["candidates"] if c["id"] == task["result"]["candidateId"])
    assert original["stale"]
    latest = state["project"]["scenes"][0]["creative"]["image"]
    await select(client, pid, await generate(client, pid, "shot_image", target=sid, frame="last"))
    async with Session() as db:
        project = await db.get(Project, pid)
        scene = await db.get(Scene, sid)
        with pytest.raises(AppError) as stale:
            await validate_derived_tail(db, project, scene, {"key": latest["key"]}, tail["asset_id"])
        assert stale.value.code == "LAST_FRAME_STALE"


async def test_tail_refuses_selected_but_outdated_first_frame(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    await select(client, pid, await generate(client, pid, "shot_image", target=sid))
    state = await fetch(client, pid)
    sc = state["project"]["scenes"][0]
    shot = {**sc["creative"]["shot"], "composition": "手部与按钮特写"}
    edited = await client.patch(
        f"/api/creative/scenes/{sid}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert edited.status_code == 200, edited.text
    from test_creative import confirm

    await confirm(client, pid, "shots")
    spy = AsyncMock(side_effect=AssertionError("A stale reference must not generate"))
    monkeypatch.setattr(providers().image, "generate", spy)
    denied = await client.post(
        f"/api/creative/projects/{pid}/generate",
        json={"operation": "shot_image", "target": sid, "frame": "last"},
    )
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "FIRST_FRAME_REQUIRED"
    spy.assert_not_awaited()
