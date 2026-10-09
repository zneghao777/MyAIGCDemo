from copy import deepcopy
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.core.db import Session
from app.models import Project, Scene
from app.providers import providers
from app.schemas.creative import Location
from app.services import creative as flow
from app.services.resources import project_out
from test_creative import setup, fetch, generate, select, confirm


async def test_name_edit_preserves_confirmation_and_visual_edit_invalidates(client):
    async with Session() as db:
        p = Project(name="环境测试", creative={"version": 1, "shots_confirmed": True, "plan": {"locations": [{"id": "station", "name": "车站", "description": "车站"}]}})
        db.add(p)
        await db.flush()
        loc = {"version": 1, "confirmed": True, "location": {"id": "station", "name": "车站", "description": "车站", "landmarks": "站牌", "lighting": "夜晚", "palette": "暖色", "states": {}}, "image": {"key": "environment", "asset_id": "image"}}
        loc["location"] = Location.model_validate(loc["location"]).model_dump()
        loc["image"]["fingerprint"] = flow.location_fingerprint(loc, p.style)
        loc["revision"] = await flow.revision(db, p.id, "station", "location", loc)
        p.creative = {**p.creative, "locations": {"station": loc}}
        sc = Scene(project_id=p.id, order_index=0, creative={"version": 1, "shot": {"cast": {}, "lines": [], "location_id": "station", "location_revision": loc["revision"]}})
        db.add(sc)
        await db.commit()
        pid, sid, original_review = p.id, sc.id, flow.review_fingerprint(sc)
    response = await client.patch(f"/api/creative/projects/{pid}/locations/station", json={"expected": 1, "data": {**loc["location"], "name": "新车站"}})
    assert response.status_code == 200, response.text
    assert response.json()["confirmed"] is True
    async with Session() as db:
        p, sc = await db.get(Project, pid), await db.get(Scene, sid)
        assert p.creative["shots_confirmed"] is True
        assert sc.creative["version"] == 1
        assert flow.review_fingerprint(sc) == original_review
        assert await flow.pending_changes(db, sc) == (False, False)
        state = deepcopy(p.creative["locations"]["station"])
        assert state["image"]["fingerprint"] == flow.location_fingerprint(state, p.style)
        state["image"]["key"] = "replacement"
        await flow.save_location(db, p, "station", state)
        assert p.creative["shots_confirmed"] is False
        assert await flow.pending_changes(db, sc) == (True, False)
        await db.commit()


async def test_two_characters_plus_environment_fit_budget_four(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "image_max_references", 4)
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    task = await generate(client, pid, "location_image", target="station")
    f = await fetch(client, pid)
    chosen = await client.post(f"/api/creative/projects/{pid}/select", json={"candidate_id": task["result"]["candidateId"], "expected": f["project"]["creative"].get("locations", {}).get("station", {}).get("version", 0)})
    assert chosen.status_code == 200, chosen.text
    f = await fetch(client, pid)
    loc = f["project"]["creative"]["locations"]["station"]
    checked = await client.post(f"/api/creative/projects/{pid}/locations/station/confirm", json={"expected": loc["version"], "data": {}})
    assert checked.status_code == 200, checked.text
    loc = checked.json()
    f = await fetch(client, pid)
    sc = f["project"]["scenes"][0]
    response = await client.patch(f"/api/creative/scenes/{sid}", json={"expected": sc["creative"]["version"], "data": {**sc["creative"]["shot"], "location_revision": loc["revision"]}})
    assert response.status_code == 200, response.text
    await confirm(client, pid, "shots")
    quote = await client.post(f"/api/creative/projects/{pid}/estimate", json={"operation": "shot_image", "target": sid})
    assert quote.status_code == 200, quote.text
    assert quote.json()["targets"][0]["id"] == sid
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    await generate(client, pid, "shot_image", target=sid)
    assert len(spy.call_args.args[3]) == 3


async def test_storyboard_prompt_uses_configured_combined_budget(env, monkeypatch):
    monkeypatch.setattr(get_settings(), "image_max_references", 4)
    spy = AsyncMock(side_effect=RuntimeError("capture prompt"))
    monkeypatch.setattr(providers().llm, "structured", spy)
    task = SimpleNamespace(payload={"creative": {"operation": "storyboard", "input": {}, "request": {}}})
    with pytest.raises(RuntimeError, match="capture prompt"):
        await flow.execute_candidate(None, task, AsyncMock(), AsyncMock())
    instruction = spy.call_args.args[1]
    assert "参考图预算为 4 张" in instruction
    assert "角色与环境参考图合计" in instruction
    assert "减少同框角色数或拆分" in instruction


async def test_deleted_response_keys_do_not_rewrite_legacy_data(client):
    p = (await client.post("/api/projects", json={"name": "历史键"})).json()
    async with Session() as db:
        row = await db.get(Project, p["id"])
        row.creative = {"version": 1, "stage": "generation"}
        await db.commit()
        assert "stage" not in (await project_out(db, row))["creative"]
        assert row.creative["stage"] == "generation"
    response = await client.get(f"/api/creative/projects/{p['id']}")
    assert response.status_code == 200, response.text
    assert "stage" not in response.json()["project"]["creative"]
    assert "visualAudit" not in response.json()["capabilities"]
    assert all(isinstance(response.json()["capabilities"][key], bool) for key in ("intro", "watermark", "bgmPresets"))
