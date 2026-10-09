"""Storyboard completion applies valid results while retaining selectable history."""
from copy import deepcopy
from unittest.mock import AsyncMock

from test_creative import fetch, generate, setup
from app.providers import providers
from app.schemas.creative import Storyboard
from app.tasks.execute import execute_job


async def test_auto_apply_and_select_history(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    before = await fetch(client, pid)
    previous = next(c for c in before["candidates"] if c["kind"] == "storyboard" and c["selected"])
    shot = deepcopy(p["scenes"][0]["creative"]["shot"])
    shot["title"] = "新的开场"
    monkeypatch.setattr(providers().llm, "structured", AsyncMock(return_value=Storyboard(scenes=[shot])))
    task = await generate(client, pid, "storyboard", auto_apply=True, nonce="auto-apply")
    assert task["result"]["applied"] is True
    current = await fetch(client, pid)
    assert current["project"]["scenes"][0]["title"] == "新的开场"
    assert not current["project"]["creative"]["shots_confirmed"]
    assert next(c for c in current["candidates"] if c["id"] == task["result"]["candidateId"])["selected"]
    response = await client.post(f"/api/creative/projects/{pid}/select", json={
        "candidate_id": previous["id"], "expected": current["project"]["creative"]["version"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["scenes"][0]["title"] == p["scenes"][0]["title"]


async def test_auto_apply_preserves_newer_edits_and_incomplete_results(client, monkeypatch):
    from app.core.errors import AppError

    p = await setup(client, monkeypatch)
    pid = p["id"]
    shot = deepcopy(p["scenes"][0]["creative"]["shot"])
    monkeypatch.setattr(providers().llm, "structured", AsyncMock(return_value=Storyboard(scenes=[shot])))
    response = await client.post(f"/api/creative/projects/{pid}/generate", json={
        "operation": "storyboard", "auto_apply": True, "nonce": "while-editing",
    })
    assert response.status_code == 202
    edited = {**shot, "title": "保留我的编辑"}
    changed = await client.patch(f"/api/creative/scenes/{p['scenes'][0]['id']}", json={
        "expected": p["scenes"][0]["creative"]["version"], "data": edited,
    })
    assert changed.status_code == 200, changed.text
    await execute_job(response.json()["taskId"])
    task = (await client.get("/api/tasks/" + response.json()["taskId"])).json()
    assert task["status"] == "done" and task["result"]["applied"] is False
    assert (await fetch(client, pid))["project"]["scenes"][0]["title"] == "保留我的编辑"
    monkeypatch.setattr(providers().llm, "structured", AsyncMock(side_effect=AppError(
        "PROVIDER_OUTPUT_INVALID", "未完整生成", 422,
        {"rawValue": {"scenes": []}, "validationIssues": [{"loc": ["scenes"], "type": "too_short", "msg": "empty"}]},
    )))
    invalid = await generate(client, pid, "storyboard", auto_apply=True, nonce="incomplete")
    assert invalid["result"]["draft"] and not invalid["result"]["applied"]
    assert (await fetch(client, pid))["project"]["scenes"][0]["title"] == "保留我的编辑"


async def test_narration_in_dialogue_is_normalized_and_existing_draft_can_be_selected(client, monkeypatch):
    from app.core.errors import AppError
    from app.core.db import Session
    from app.models import Candidate

    p = await setup(client, monkeypatch)
    raw = {"scenes": [deepcopy(p["scenes"][0]["creative"]["shot"])]}
    shot = raw["scenes"][0]
    shot["lines"].append({"id": "opening-narration", "speaker_id": None, "text": "夜色渐深。"})
    shot["audio_order"] = ["opening-narration", *[x["id"] for x in shot["lines"][:-1]], *[x["id"] for x in shot["narration"]]]
    shot["spatial_relations"][shot["location_id"]] = "车站入口位于画面左侧。"
    model = AsyncMock(side_effect=AppError("PROVIDER_OUTPUT_INVALID", "schema", 422, {"rawValue": raw}))
    monkeypatch.setattr(providers().llm, "structured", model)
    task = await generate(client, p["id"], "storyboard", auto_apply=True, nonce="misplaced-narration")
    assert task["result"]["applied"] and not task["result"]["draft"], task["result"]
    f = await fetch(client, p["id"])
    active = f["project"]["scenes"][0]["creative"]["shot"]
    assert active["narration"][-1]["id"] == "opening-narration"
    assert active["audio_order"] == shot["audio_order"]
    assert "车站入口位于画面左侧。" in active["composition"]
    # Recreate a pre-fix saved candidate to cover the actual historical selection path.
    async with Session() as db:
        original = await db.get(Candidate, task["result"]["candidateId"])
        old = Candidate(project_id=p["id"], entity_id=p["id"], kind="storyboard", fingerprint=original.fingerprint,
                        data={"value": raw, "draft": True, "validation_issues": [{"code": "value_error"}]})
        db.add(old)
        await db.commit()
        old_id = old.id
    response = await client.post(f"/api/creative/projects/{p['id']}/select", json={
        "candidate_id": old_id, "expected": f["project"]["creative"]["version"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["scenes"][0]["creative"]["shot"]["narration"][-1]["id"] == "opening-narration"
    assert model.await_count == 1
