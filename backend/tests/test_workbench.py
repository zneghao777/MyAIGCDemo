"""Isolated contracts for publication, dependency-specific invalidation and history."""

from copy import deepcopy

from test_creative import fetch, generate, select, setup


async def test_draft_save_does_not_unconfirm_and_publish_uses_current_text(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, st = p["id"], p["creative"]
    draft = {**st["plan"], "synopsis": "尚未确认的新梗概"}
    r = await client.patch(
        f"/api/creative/projects/{pid}/plan", json={"expected": st["version"], "data": draft}
    )
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["plan_draft"]["synopsis"] == draft["synopsis"]
    assert saved["plan"]["synopsis"] != draft["synopsis"]
    assert all(saved[k] for k in ("plan_confirmed", "cast_confirmed", "shots_confirmed"))
    current = {**draft, "synopsis": "确认按钮中的最新文字"}
    r = await client.post(
        f"/api/creative/projects/{pid}/confirm/plan",
        json={"expected": saved["version"], "data": {"plan": current}},
    )
    assert r.status_code == 200, r.text
    result = r.json()["creative"]
    assert result["plan"]["synopsis"] == current["synopsis"]
    assert result["cast_confirmed"] and not result["shots_confirmed"]
    assert not result["plan_draft"]
    old = await client.post(
        f"/api/creative/projects/{pid}/confirm/plan",
        json={"expected": st["version"], "data": {"plan": draft}},
    )
    assert old.status_code == 409
    assert (await fetch(client, pid))["project"]["creative"]["plan"] == current


async def test_title_and_persona_draft_do_not_invalidate_assets(client, monkeypatch):
    p = await setup(client, monkeypatch)
    plan = deepcopy(p["creative"]["plan"])
    plan["title"] = "只改片名"
    plan["characters"][0]["personality"] = "更勇敢的人物初稿"
    r = await client.post(
        f"/api/creative/projects/{p['id']}/confirm/plan",
        json={"expected": p["creative"]["version"], "data": {"plan": plan}},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["creative"]["shots_confirmed"] and result["creative"]["cast_confirmed"]
    assert result["characters"] == p["characters"]


async def test_style_invalidates_images_but_retains_voices_and_history(client, monkeypatch):
    p = await setup(client, monkeypatch)
    r = await client.post(
        f"/api/creative/projects/{p['id']}/confirm/plan",
        json={
            "expected": p["creative"]["version"],
            "data": {"plan": {**p["creative"]["plan"], "style": "水墨"}},
        },
    )
    assert r.status_code == 200, r.text
    f = await fetch(client, p["id"])
    assert not f["project"]["creative"]["cast_confirmed"]
    assert all(not c["image"] and c["voice"] for c in f["readiness"])
    assert all(not c["creative"]["confirmed"] for c in f["project"]["characters"])
    history = (await client.get(f"/api/creative/projects/{p['id']}/history")).json()
    assert len({x["event"]["id"] for x in history[:3]}) == 1
    assert all(x["changes"] for x in history[:3])


async def test_restore_is_new_version_and_checks_concurrency(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    ch = p["characters"][0]
    rid = ch["creative"]["revision"]
    before = len((await fetch(client, pid))["revisions"])
    path = f"/api/creative/projects/{pid}/history/{rid}"
    impact = (await client.get(path + "/impact")).json()
    r = await client.post(
        path + "/restore",
        json={"expected": impact["expected"], "data": {"projectExpected": impact["projectExpected"]}},
    )
    assert r.status_code == 200, r.text
    f = await fetch(client, pid)
    new = next(c for c in f["project"]["characters"] if c["id"] == ch["id"])
    assert new["creative"]["version"] > ch["creative"]["version"]
    assert new["creative"]["revision"] != rid and not new["creative"]["confirmed"]
    assert len(f["revisions"]) > before and any(r["id"] == rid for r in f["revisions"])
    r = await client.post(
        path + "/restore",
        json={"expected": impact["expected"], "data": {"projectExpected": impact["projectExpected"]}},
    )
    assert r.status_code == 409


async def test_stage_finalization_is_atomic_and_preserves_pins(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, ch = p["id"], p["characters"][0]
    await select(
        client, pid, await generate(client, pid, "voice_preview", target=ch["id"], voice_id="voice-new")
    )
    f = await fetch(client, pid)
    r = await client.post(
        f"/api/creative/projects/{pid}/confirm/cast",
        json={"expected": f["project"]["creative"]["version"], "data": {"finalize_characters": True}},
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["creative"]["cast_confirmed"]
    current = next(c for c in p["characters"] if c["id"] == ch["id"])
    assert p["scenes"][0]["creative"]["shot"]["cast"][ch["id"]] == current["creative"]["revision"]
    history = (await client.get(f"/api/creative/projects/{pid}/history")).json()
    assert len({x["event"]["id"] for x in history[:4]}) == 1


async def test_sync_is_explicit_and_project_scoped(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, ch = p["id"], p["characters"][0]
    draft = deepcopy(p["creative"]["plan"])
    draft["characters"][0]["personality"] = "显式同步的新性格"
    r = await client.patch(
        f"/api/creative/projects/{pid}/plan", json={"expected": p["creative"]["version"], "data": draft}
    )
    assert r.status_code == 200
    r = await client.post(
        f"/api/creative/projects/{pid}/sync-character/{ch['id']}",
        json={
            "expected": ch["creative"]["version"],
            "data": {"projectExpected": r.json()["version"], "index": 0, "fields": ["personality"]},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["persona"]["personality"] == "显式同步的新性格"
    assert r.json()["image"] == ch["creative"]["image"]
    assert not r.json()["confirmed"]


async def test_initial_brief_used_for_generation_input(client):
    from app.core.db import Session
    from app.models import Project
    from app.services.creative import current_input

    p = (await client.post("/api/projects", json={"name": "隔离创意设置"})).json()
    p = (await client.post(f"/api/creative/projects/{p['id']}/start")).json()
    data = {"idea": "新创意", "style": "手绘动画", "ratio": "9:16", "duration": 60, "scene_count": 6}
    r = await client.patch(
        f"/api/creative/projects/{p['id']}/brief", json={"expected": p["creative"]["version"], "data": data}
    )
    assert r.status_code == 200, r.text
    async with Session() as db:
        row = await db.get(Project, p["id"])
        inp = await current_input(db, row, "plan")
        assert all(inp[k] == v for k, v in data.items())


async def test_legacy_default_fields_do_not_create_false_impact():
    from test_creative import plan_data

    from app.schemas.creative import Plan
    from app.services.workbench import plan_impact

    old = plan_data()
    for c in old["characters"]:
        c.pop("voice_mode", None)
        c.pop("base_pitch", None)
    assert plan_impact(old, Plan.model_validate(old).model_dump())["changed"] == []


async def test_cast_confirmation_rolls_back_if_any_character_not_ready(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    ch = p["characters"][0]
    await select(
        client, pid, await generate(client, pid, "voice_preview", target=ch["id"], voice_id="new-voice")
    )
    bad = p["characters"][1]
    r = await client.patch(
        f"/api/creative/characters/{bad['id']}",
        json={
            "expected": bad["creative"]["version"],
            "data": {**bad["creative"]["persona"], "voice_description": "changed voice spec"},
        },
    )
    assert r.status_code == 200
    before = await fetch(client, pid)
    r = await client.post(
        f"/api/creative/projects/{pid}/confirm/cast",
        json={"expected": before["project"]["creative"]["version"], "data": {"finalize_characters": True}},
    )
    assert r.status_code == 409
    after = await fetch(client, pid)
    assert after["project"] == before["project"]
    assert len(after["revisions"]) == len(before["revisions"])


async def test_shot_restore_and_cross_project_rejection(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, sc = p["id"], p["scenes"][0]
    rid = sc["creative"]["revision"]
    r = await client.patch(
        f"/api/creative/scenes/{sc['id']}",
        json={
            "expected": sc["creative"]["version"],
            "data": {**sc["creative"]["shot"], "action": "new action"},
        },
    )
    assert r.status_code == 200, r.text
    url = f"/api/creative/projects/{pid}/history/{rid}"
    impact = (await client.get(url + "/impact")).json()
    r = await client.post(
        url + "/restore",
        json={"expected": impact["expected"], "data": {"projectExpected": impact["projectExpected"]}},
    )
    assert r.status_code == 200, r.text
    new = (await fetch(client, pid))["project"]["scenes"][0]["creative"]
    assert new["shot"] == sc["creative"]["shot"]
    assert new["version"] > sc["creative"]["version"]
    other = (await client.post("/api/projects", json={"name": "别的隔离项目"})).json()
    r = await client.get(f"/api/creative/projects/{other['id']}/history/{rid}/impact")
    assert r.status_code == 422
