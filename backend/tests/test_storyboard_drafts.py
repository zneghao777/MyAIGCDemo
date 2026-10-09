"""Keep a billed semantic failure available for explicit, cost-free correction."""

from copy import deepcopy
from unittest.mock import AsyncMock

from test_creative import fetch, generate, setup

from app.core.config import get_settings
from app.core.errors import AppError
from app.providers import providers
from app.schemas.creative import Storyboard


async def test_unavailable_state_uses_base_reference_with_original_preserved(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    task = await generate(client, pid, "location_image", target="station")
    f = await fetch(client, pid)
    selected = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": task["result"]["candidateId"], "expected": 0},
    )
    assert selected.status_code == 200, selected.text
    location = selected.json()["creative"]["locations"]["station"]
    confirmed = await client.post(
        f"/api/creative/projects/{pid}/locations/station/confirm",
        json={"expected": location["version"], "data": {}},
    )
    assert confirmed.status_code == 200, confirmed.text
    location = confirmed.json()
    f = await fetch(client, pid)
    shot = deepcopy(f["project"]["scenes"][0]["creative"]["shot"])
    shot.update(location_revision=location["revision"], location_state="灯未亮")
    bad_value = Storyboard(scenes=[shot])
    model = AsyncMock(return_value=bad_value)
    monkeypatch.setattr(providers().llm, "structured", model)
    monkeypatch.setattr(get_settings(), "cost_unit_price_json", {"llmPerMToken": 1000})
    monkeypatch.setattr(get_settings(), "image_max_references", 3)
    task = await generate(client, pid, "storyboard", nonce="invalid-state-draft")
    assert task["status"] == "done" and not task["result"]["draft"]
    assert task["costCents"] == task["estimatedCostCents"] > 0
    assert "必须为空字符串" in model.call_args.args[1]
    f = await fetch(client, pid)
    original = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    assert original["data"]["original_value"]["scenes"][0]["location_state"] == "灯未亮"
    assert original["data"]["value"]["scenes"][0]["location_state"] == ""
    assert "灯未亮" in original["data"]["value"]["scenes"][0]["start_state"]
    assert original["data"]["validation_issues"] == []
    old_ids = [s["id"] for s in f["project"]["scenes"]]
    assert [s["id"] for s in (await fetch(client, pid))["project"]["scenes"]] == old_ids
    fixed = deepcopy(original["data"]["value"])
    fixed["scenes"][0]["location_state"] = ""
    edited = await client.patch(
        f"/api/creative/projects/{pid}/candidates/{original['id']}",
        json={"expected": f["project"]["creative"]["version"], "data": fixed},
    )
    assert edited.status_code == 200, edited.text
    child_id = edited.json()["candidateId"]
    f = await fetch(client, pid)
    child = next(c for c in f["candidates"] if c["id"] == child_id)
    assert child["data"]["parent_candidate_id"] == original["id"] and child["taskId"] == original["taskId"]
    assert not child["data"]["draft"] and child["data"]["validation_issues"] == []
    accepted = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": child_id, "expected": f["project"]["creative"]["version"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["scenes"][0]["creative"]["shot"]["location_state"] == ""
    f = await fetch(client, pid)
    original_after = next(c for c in f["candidates"] if c["id"] == original["id"])
    assert original_after["data"]["value"] == original["data"]["value"]
    assert model.await_count == 1


async def test_schema_invalid_json_is_kept_as_raw_draft_and_repair_is_strict(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    raw = {"scenes": [deepcopy(p["scenes"][0]["creative"]["shot"])]}
    raw["scenes"][0]["camera_move"] = "环绕"
    model = AsyncMock(
        side_effect=AppError(
            "PROVIDER_OUTPUT_INVALID",
            "分镜结构校验失败",
            422,
            {
                "rawValue": raw,
                "validationIssues": [
                    {
                        "loc": ["scenes", 0, "camera_move"],
                        "type": "literal_error",
                        "msg": "镜头运动必须使用合法枚举",
                    }
                ],
            },
        )
    )
    monkeypatch.setattr(providers().llm, "structured", model)
    task = await generate(client, pid, "storyboard", nonce="invalid-enum-raw")
    assert task["status"] == "done" and task["result"]["draft"]
    f = await fetch(client, pid)
    original = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    assert original["data"]["value"] == raw and original["data"]["validation_stage"] == "schema"
    assert original["data"]["validation_issues"][0]["path"] == ["scenes", 0, "camera_move"]
    denied = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": original["id"], "expected": f["project"]["creative"]["version"]},
    )
    assert denied.status_code == 422 and denied.json()["error"]["code"] == "VALIDATION_ERROR"
    rejected_edit = await client.patch(
        f"/api/creative/projects/{pid}/candidates/{original['id']}",
        json={"expected": f["project"]["creative"]["version"], "data": raw},
    )
    assert rejected_edit.status_code == 422
    fixed = deepcopy(raw)
    fixed["scenes"][0]["camera_move"] = "固定"
    selected = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": original["id"], "expected": f["project"]["creative"]["version"], "data": fixed},
    )
    assert selected.status_code == 200, selected.text
    f = await fetch(client, pid)
    child = next(c for c in f["candidates"] if c["selected"])
    assert child["data"]["source"] == "manual-edit" and child["data"]["parent_candidate_id"] == original["id"]
    assert next(c for c in f["candidates"] if c["id"] == original["id"])["data"]["value"] == raw
    assert model.await_count == 1
