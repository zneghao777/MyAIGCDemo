"""Exercise persistence and quoting with mocked paid image calls."""
from unittest.mock import AsyncMock

from test_creative import fetch, generate, select, setup
from app.core.config import get_settings
from app.core.db import Session
from app.core.errors import AppError
from app.models import Task
from app.providers import providers
from app.tasks.execute import execute_job


async def test_portrait_and_turnaround_are_quoted_selected_and_reused(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, cid = p["id"], p["characters"][0]["id"]
    monkeypatch.setattr(get_settings(), "cost_unit_price_json", {"imagePerCall": 10})
    quote = await client.post(f"/api/creative/projects/{pid}/estimate", json={"operation": "character_image", "target": cid})
    assert quote.status_code == 200, quote.text
    assert quote.json()["calls"] == 2 and quote.json()["estimateCents"] == 20
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    task = await generate(client, pid, "character_image", target=cid, nonce="package")
    assert spy.await_count == 2
    assert spy.await_args_list[0].args[1] == "9:16"
    sheet_call = spy.await_args_list[1].args
    assert sheet_call[1] == "16:9" and len(sheet_call[3]) == 1
    assert "正面、侧面、背面" in sheet_call[0]
    f = await fetch(client, pid)
    candidate = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    assert candidate["data"]["turnaround"]["url"].startswith("https://media.example/")
    assert not candidate["data"].get("package_pending")
    p = await select(client, pid, task)
    ch = next(c for c in p["characters"] if c["id"] == cid)
    assert ch["creative"]["image"]["turnaround"]["asset_id"]
    changed = await client.patch(f"/api/creative/characters/{cid}", json={"expected": ch["creative"]["version"], "data": {**ch["creative"]["persona"], "image_prompt": "保持人物身份，改穿深蓝色外套"}})
    assert changed.status_code == 200, changed.text
    spy.reset_mock()
    await generate(client, pid, "character_image", target=cid, use_reference=True, nonce="reference")
    assert len(spy.await_args_list[0].args[3]) == 1
    restored = await client.patch(f"/api/creative/characters/{cid}", json={"expected": changed.json()["version"], "data": ch["creative"]["persona"]})
    assert restored.status_code == 200, restored.text
    res = await client.post(f"/api/creative/characters/{cid}/confirm", json={"expected": restored.json()["version"], "data": {}})
    assert res.status_code == 200, res.text
    lib = await client.post(f"/api/creative/characters/{cid}/publish-library")
    assert lib.status_code == 200, lib.text
    assert lib.json()["data"]["image"]["turnaround"]["key"].startswith("library/")
    reused = await client.post(f"/api/creative/projects/{pid}/reuse/{lib.json()['id']}")
    assert reused.status_code == 200, reused.text
    new = reused.json()["characters"][-1]
    assert new["creative"]["image"]["turnaround"]["key"].startswith(f"projects/{pid}/")


async def test_sheet_failure_preserves_portrait_and_retry_reuses_paid_output(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, cid = p["id"], p["characters"][0]["id"]
    original = providers().image.generate
    spy = AsyncMock(side_effect=[await original(), AppError("IMAGE_FAILED", "三视图生成失败")])
    monkeypatch.setattr(providers().image, "generate", spy)
    res = await client.post(f"/api/creative/projects/{pid}/generate", json={"operation": "character_image", "target": cid, "nonce": "partial"})
    assert res.status_code == 202, res.text
    tid = res.json()["taskId"]
    await execute_job(tid)
    task = (await client.get(f"/api/tasks/{tid}")).json()
    assert task["status"] == "failed"
    f = await fetch(client, pid)
    partial = next(c for c in f["candidates"] if c.get("taskId") == tid)
    assert partial["url"] and partial["data"]["package_pending"]
    assert f["project"]["characters"][0]["creative"]["image"]["candidate_id"] != partial["id"]
    async with Session() as db:
        row = await db.get(Task, tid)
        row.status = "queued"
        await db.commit()
    choosing = await client.post(f"/api/creative/projects/{pid}/select", json={"candidate_id": partial["id"], "expected": f["project"]["characters"][0]["creative"]["version"]})
    assert choosing.status_code == 409 and choosing.json()["error"]["code"] == "CANDIDATE_GENERATING"
    resumed = AsyncMock(wraps=original)
    monkeypatch.setattr(providers().image, "generate", resumed)
    await execute_job(tid)
    assert resumed.await_count == 1
    task = (await client.get(f"/api/tasks/{tid}")).json()
    assert task["status"] == "done" and task["result"]["candidateId"] == partial["id"]
    f = await fetch(client, pid)
    candidate = next(c for c in f["candidates"] if c["id"] == partial["id"])
    assert candidate["data"]["turnaround"]["asset_id"] and not candidate["data"].get("package_pending")


async def test_scene_reference_generation_uses_selected_environment(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    location_id = p["creative"]["plan"]["locations"][0]["id"]
    task = await generate(client, pid, "location_image", target=location_id)
    f = await fetch(client, pid)
    candidate = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    chosen = await client.post(f"/api/creative/projects/{pid}/select", json={"candidate_id": candidate["id"], "expected": 0})
    assert chosen.status_code == 200, chosen.text
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    await generate(client, pid, "location_image", target=location_id, use_reference=True, nonce="environment-reference")
    assert spy.await_count == 1 and len(spy.call_args.args[3]) == 1
    assert "保持地标和空间结构" in spy.call_args.args[0]


async def test_standalone_turnaround_uses_master_and_costs_one_image(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, cid = p["id"], p["characters"][0]["id"]
    quote = await client.post(f"/api/creative/projects/{pid}/estimate", json={"operation": "character_image", "target": cid, "view": "turnaround"})
    assert quote.status_code == 200 and quote.json()["calls"] == 1
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    task = await generate(client, pid, "character_image", target=cid, view="turnaround")
    assert spy.await_count == 1 and spy.call_args.args[1] == "16:9"
    assert len(spy.call_args.args[3]) == 1 and "全身三视图" in spy.call_args.args[0]
    chosen = await select(client, pid, task)
    ch = next(c for c in chosen["characters"] if c["id"] == cid)
    assert ch["creative"]["views"]["turnaround"]["asset_id"]
    assert ch["creative"]["image"]["key"] == p["characters"][0]["creative"]["image"]["key"]
