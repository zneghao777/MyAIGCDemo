from copy import deepcopy
from unittest.mock import AsyncMock

from app.core.errors import AppError
from app.providers import providers
from app.services.storyboard_recovery import normalize, parse_text
from test_creative import setup, fetch, generate, confirm


async def test_visual_text_is_recovered_without_paid_retry(client, monkeypatch):
    p = await setup(client, monkeypatch)
    raw = {"scenes": [deepcopy(p["scenes"][0]["creative"]["shot"])]}
    raw["scenes"][0]["lines"].append(
        {"id": "screen-message", "speaker_id": None, "text": "手机屏幕亮起，一条匿名消息弹出。"}
    )
    model = AsyncMock(
        side_effect=AppError(
            "PROVIDER_OUTPUT_INVALID", "schema", 422, {"rawValue": raw, "validationIssues": []}
        )
    )
    monkeypatch.setattr(providers().llm, "structured", model)
    task = await generate(client, p["id"], "storyboard", nonce="visual-message")
    assert task["status"] == "done" and not task["result"]["draft"]
    f = await fetch(client, p["id"])
    candidate = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    assert candidate["data"]["original_value"] == raw
    assert "手机屏幕亮起" in candidate["data"]["value"]["scenes"][0]["action"]
    assert model.await_count == 1


async def test_noop_confirmation_does_not_stale_storyboard(client, monkeypatch):
    p = await setup(client, monkeypatch)
    task = await generate(client, p["id"], "storyboard", nonce="stable-content")
    await confirm(client, p["id"], "cast")
    f = await fetch(client, p["id"])
    candidate = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    assert not candidate["stale"]


async def test_local_recovery_route_keeps_original_and_is_idempotent(client, monkeypatch):
    p = await setup(client, monkeypatch)
    raw = {"scenes": [deepcopy(p["scenes"][0]["creative"]["shot"])]}
    raw["scenes"][0]["lines"][0]["speaker_id"] = "unknown-speaker"
    monkeypatch.setattr(
        providers().llm,
        "structured",
        AsyncMock(side_effect=AppError("PROVIDER_OUTPUT_INVALID", "schema", 422, {"rawValue": raw})),
    )
    task = await generate(client, p["id"], "storyboard", nonce="unknown-speaker")
    candidate_id = task["result"]["candidateId"]
    f = await fetch(client, p["id"])
    payload = {"expected": f["project"]["creative"]["version"], "data": {}}
    url = f"/api/creative/projects/{p['id']}/candidates/{candidate_id}/repair"
    response = await client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert not response.json()["ready"]
    again = await client.post(url, json=payload)
    assert again.json()["candidateId"] == response.json()["candidateId"]
    f = await fetch(client, p["id"])
    assert next(c for c in f["candidates"] if c["id"] == candidate_id)["data"]["value"] == raw
    assert [s["id"] for s in f["project"]["scenes"]] == [s["id"] for s in p["scenes"]]


def test_unescaped_quotes_preserve_dialogue_and_bad_json_is_not_guessed():
    value, changes = parse_text('{"scenes":[{"lines":[{"text":"投稿——"匿名告白"！",}],}],}')
    assert value["scenes"][0]["lines"][0]["text"] == '投稿——"匿名告白"！'
    assert len(changes) == 2
    assert parse_text('{"scenes": [truncated')[0] is None


def test_redundant_main_outfit_alias_reuses_main_but_different_costume_is_not_dropped():
    from app.services.creative import image_fingerprint

    persona = {
        "name": "林小美",
        "clothing": "粉色卡通睡衣，毛绒拖鞋",
        "variants": {"睡衣": "粉色卡通睡衣", "礼服": "蓝色长裙礼服"},
    }
    state = {
        "persona": persona,
        "revision": "confirmed-role",
        "confirmed": True,
        "image": {"key": "saved-main", "fingerprint": image_fingerprint(persona, "日漫")},
    }
    inp = {"cast": {"role": state}, "plan": {"style": "日漫"}, "locations": {}}
    base = {"scenes": [{"cast": {"role": "confirmed-role"}, "variants": {"role": "睡衣"}, "character_views": {"role": "main"}}]}
    fixed, changes = normalize(base, inp)
    assert fixed["scenes"][0]["variants"] == {} and changes
    assert fixed["scenes"][0]["character_views"] == {}
    assert base["scenes"][0]["variants"]["role"] == "睡衣"
    base["scenes"][0]["variants"]["role"] = "礼服"
    fixed, changes = normalize(base, inp)
    assert fixed["scenes"][0]["variants"]["role"] == "礼服"


async def test_real_story_change_stales_draft_but_can_explicitly_recover(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid = p["id"]
    task = await generate(client, pid, "storyboard", nonce="before-story-change")
    f = await fetch(client, pid)
    plan = deepcopy(f["project"]["creative"]["plan"])
    plan["synopsis"] = "两位信使发现信件中的真正秘密"
    edited = await client.patch(
        f"/api/creative/projects/{pid}/plan",
        json={"expected": f["project"]["creative"]["version"], "data": plan},
    )
    assert edited.status_code == 200
    await confirm(client, pid, "plan")
    await confirm(client, pid, "cast")
    f = await fetch(client, pid)
    candidate = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    assert candidate["stale"]
    recovered = await client.post(
        f"/api/creative/projects/{pid}/candidates/{candidate['id']}/repair",
        json={"expected": f["project"]["creative"]["version"], "data": {}},
    )
    assert recovered.status_code == 200 and recovered.json()["ready"]
    f = await fetch(client, pid)
    child = next(c for c in f["candidates"] if c["id"] == recovered.json()["candidateId"])
    assert not child["stale"] and child["data"]["parent_candidate_id"] == candidate["id"]


async def test_ai_repair_quotes_single_new_call_and_rejects_foreign_candidate(client, monkeypatch):
    p = await setup(client, monkeypatch)
    task = await generate(client, p["id"], "storyboard", nonce="repair-target")
    cid = task["result"]["candidateId"]
    quote = await client.post(
        f"/api/creative/projects/{p['id']}/estimate",
        json={"operation": "storyboard", "target": cid, "nonce": "one-repair"},
    )
    assert quote.status_code == 200
    board = deepcopy(p["scenes"][0]["creative"]["shot"])
    from app.schemas.creative import Storyboard

    model = AsyncMock(return_value=Storyboard(scenes=[board]))
    monkeypatch.setattr(providers().llm, "structured", model)
    repaired = await generate(client, p["id"], "storyboard", target=cid, nonce="one-repair")
    assert model.await_count == 1
    assert model.call_args.args[2]["repair"]["candidate_id"] == cid
    assert not repaired["result"]["draft"]
    foreign = (await client.post("/api/projects", json={"name": "别人的项目"})).json()
    denied = await client.post(
        f"/api/creative/projects/{foreign['id']}/candidates/{cid}/repair", json={"expected": 0, "data": {}}
    )
    assert denied.status_code in (409, 422)


def test_base_outfit_traits_and_unavailable_turnaround_use_confirmed_main():
    from app.services.creative import image_fingerprint

    persona = {"name": "阿茶", "clothing": "素色棉麻长裙，外罩一件青灰色围裙", "accessories": "左腕银镯子", "hair": "长发散落肩头",
               "variants": {"初登场": "素色棉麻长裙，青灰色围裙，银镯子", "结尾": "无围裙，赤足", "常态": "素色棉麻长裙，披发"}}
    state = {"persona": persona, "revision": "role-v1", "confirmed": True, "image": {"key": "main", "fingerprint": image_fingerprint(persona, "写实")}}
    inp = {"cast": {"role": state}, "plan": {"style": "写实"}, "locations": {}}
    for variant in ("初登场", "常态", "结尾"):
        value = {"scenes": [{"cast": {"role": "role-v1"}, "variants": {"role": variant}, "character_views": {"role": "turnaround"}}]}
        fixed, _ = normalize(value, inp)
        assert fixed["scenes"][0]["character_views"] == {}
        assert fixed["scenes"][0]["variants"] == ({"role": "结尾"} if variant == "结尾" else {})
