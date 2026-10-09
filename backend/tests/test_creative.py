"""Business contracts: revisions, speaker identity, partial regeneration and actual ffmpeg."""

from copy import deepcopy
from unittest.mock import AsyncMock
from app.schemas.creative import Persona, Plan, Storyboard, VoiceMatches
from app.providers import providers
from app.tasks.execute import execute_job


async def test_forced_line_take_preserves_other_speakers(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    await select(client, pid, await generate(client, pid, "shot_audio", target=sid))
    old = (await fetch(client, pid))["scenes"][0]["segments"]
    spy = AsyncMock(wraps=providers().tts.synthesize)
    monkeypatch.setattr(providers().tts, "synthesize", spy)
    task = await generate(
        client, pid, "shot_audio", target=sid, regenerate_line_ids=[old[0]["line"]["id"]], nonce="take-two"
    )
    await select(client, pid, task)
    new = (await fetch(client, pid))["scenes"][0]["segments"]
    assert spy.await_count == 1
    assert new[0]["key"] != old[0]["key"]
    assert [x["key"] for x in new[1:]] == [x["key"] for x in old[1:]]


async def test_tts_model_change_invalidates_audio_only(client, monkeypatch):
    from app.core.config import get_settings

    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    for op in ["shot_image", "shot_audio"]:
        await select(client, pid, await generate(client, pid, op, target=sid))
    monkeypatch.setattr(get_settings(), "minimax_tts_model", "another-model")
    sc = (await fetch(client, pid))["scenes"][0]
    assert sc["audio_stale"] and not sc["image_stale"]


async def test_narration_can_precede_and_interleave_dialogue(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, sc = p["id"], p["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["audio_order"] = ["narrator", "line-0", "line-1"]
    r = await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert r.status_code == 200, r.text
    await confirm(client, pid, "shots")
    await select(client, pid, await generate(client, pid, "shot_audio", target=sc["id"]))
    segments = (await fetch(client, pid))["scenes"][0]["segments"]
    assert [s["line"]["id"] for s in segments] == shot["audio_order"]
    assert segments[1]["start_ms"] == segments[0]["duration_ms"] + 150


async def test_missing_variant_reference_blocks_shot_confirmation(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, c = p["id"], p["characters"][0]
    persona = {**c["creative"]["persona"], "variants": {"晚装": "黑色礼服"}}
    await client.patch(
        f"/api/creative/characters/{c['id']}", json={"expected": c["creative"]["version"], "data": persona}
    )
    await select(client, pid, await generate(client, pid, "character_image", target=c["id"]))
    f = await fetch(client, pid)
    ch = next(x for x in f["project"]["characters"] if x["id"] == c["id"])
    await client.post(
        f"/api/creative/characters/{c['id']}/confirm",
        json={"expected": ch["creative"]["version"], "data": {}},
    )
    f = await fetch(client, pid)
    sc = f["project"]["scenes"][0]
    shot = {**sc["creative"]["shot"], "variants": {c["id"]: "晚装"}}
    r = await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert r.status_code == 200  # Text design may reference a variant before producing it.
    from app.core.db import Session
    from app.models import Scene
    from app.services.creative import shot_inputs
    from app.core.errors import AppError
    import pytest
    async with Session() as db:
        row = await db.get(Scene, sc["id"])
        with pytest.raises(AppError) as error:
            await shot_inputs(db, row, need_audio=False)
        assert error.value.code == "VARIANT_REFERENCE_REQUIRED"


def plan_data():
    return dict(
        title="两个人的信",
        synopsis="两位信使交换线索",
        theme="信任",
        beats=["相遇", "误会", "解释", "和解"],
        ending="一起出发",
        duration=10,
        scene_count=1,
        ratio="16:9",
        style="电影写实",
        characters=[
            Persona(
                name="林夏", appearance="短发女子", image_prompt="短发女子", voice_description="年轻女性"
            ).model_dump(),
            Persona(
                name="老周", appearance="白发男子", image_prompt="白发男子", voice_description="年长男性"
            ).model_dump(),
        ],
        locations=[dict(id="station", name="车站", description="清晨车站")],
    )


async def fetch(client, id):
    r = await client.get(f"/api/creative/projects/{id}")
    assert r.status_code == 200, r.text
    return r.json()


async def generate(client, id, operation, **kwargs):
    r = await client.post(f"/api/creative/projects/{id}/generate", json={"operation": operation, **kwargs})
    assert r.status_code == 202, r.text
    await execute_job(r.json()["taskId"])
    task = (await client.get("/api/tasks/" + r.json()["taskId"])).json()
    assert task["status"] == "done", task
    return task


async def select(client, id, task):
    f = await fetch(client, id)
    candidate = next(x for x in f["candidates"] if x["id"] == task["result"]["candidateId"])
    p = f["project"]
    target = next((x for x in p["characters"] + p["scenes"] if x["id"] == candidate["entityId"]), p)
    r = await client.post(
        f"/api/creative/projects/{id}/select",
        json={"candidate_id": candidate["id"], "expected": target["creative"]["version"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def confirm(client, id, stage):
    f = await fetch(client, id)
    r = await client.post(
        f"/api/creative/projects/{id}/confirm/{stage}",
        json={"expected": f["project"]["creative"]["version"], "data": {}},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def setup(client, monkeypatch):
    async def llm(model, instruction, brief):
        if model is Plan:
            return Plan(**plan_data())
        if model is VoiceMatches:
            return VoiceMatches(voice_ids=["voice-a", "voice-b"], reason="测试匹配")
        raise AssertionError(model)

    monkeypatch.setattr(providers().llm, "structured", llm)
    p = (
        await client.post("/api/projects", json={"name": "创作验收", "description": "两位信使在车站交换线索"})
    ).json()
    id = p["id"]
    await client.post(f"/api/creative/projects/{id}/start")
    p = await select(client, id, await generate(client, id, "plan"))
    p = await confirm(client, id, "plan")
    for i, c in enumerate(p["characters"]):
        await select(client, id, await generate(client, id, "character_image", target=c["id"]))
        await select(
            client,
            id,
            await generate(
                client, id, "voice_preview", target=c["id"], voice_id=f"voice-{'a' if i == 0 else 'b'}"
            ),
        )
        f = await fetch(client, id)
        ch = next(x for x in f["project"]["characters"] if x["id"] == c["id"])
        r = await client.post(
            f"/api/creative/characters/{c['id']}/confirm",
            json={"expected": ch["creative"]["version"], "data": {}},
        )
        assert r.status_code == 200, r.text
    p = await confirm(client, id, "cast")
    chars = p["characters"]
    shot = dict(
        title="交接",
        cast={c["id"]: c["creative"]["revision"] for c in chars},
        location_id="station",
        action="交接信件",
        image_prompt="车站两人交接信件",
        lines=[
            dict(
                id=f"line-{i}",
                speaker_id=c["id"],
                text=f"第{i + 1}句",
                emotion="calm",
                speed=1,
                pause_after=0.2,
            )
            for i, c in enumerate(chars)
        ],
        narration=[dict(id="narrator", text="车站恢复了平静", speaker_id=None)],
    )

    async def board(model, instruction, brief):
        assert model is Storyboard
        assert brief["plan"]["title"] == "两个人的信"
        assert brief["cast"][chars[0]["id"]]["revision"] == shot["cast"][chars[0]["id"]]
        return Storyboard(scenes=[shot])

    monkeypatch.setattr(providers().llm, "structured", board)
    p = await select(client, id, await generate(client, id, "storyboard"))
    p = await confirm(client, id, "shots")
    return p


async def test_full_relationships_invalidation_and_export(client, monkeypatch, env, tmp_path):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    original = providers().tts.synthesize
    calls = []

    async def spy(text, voice, performance=None):
        calls.append((text, voice, performance))
        return await original(text, voice, performance)

    monkeypatch.setattr(providers().tts, "synthesize", spy)
    await select(client, id, await generate(client, id, "shot_image", target=sc["id"]))
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    assert [x[1] for x in calls] == ["voice-a", "voice-b", "male-qn-qingse"]
    assert calls[0][2]["emotion"] == "calm"
    f = await fetch(client, id)
    assert not f["issues"]
    assert len(f["scenes"][0]["segments"]) == 3
    seg = f["scenes"][0]["segments"]
    assert seg[1]["start_ms"] == seg[0]["duration_ms"] + 200
    # A changed line retains image and two unmodified utterances.
    sc = f["project"]["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["lines"][0]["text"] = "修改第一句"
    r = await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert r.status_code == 200, r.text
    f = await fetch(client, id)
    assert not f["scenes"][0]["image_stale"] and f["scenes"][0]["audio_stale"]
    await confirm(client, id, "shots")
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    assert len(calls) == 4 and calls[-1][0] == "修改第一句"
    # Selecting a new voice only invalidates that speaker's lines, never images/narration.
    c = f["project"]["characters"][0]
    await select(client, id, await generate(client, id, "voice_preview", target=c["id"], voice_id="voice-c"))
    f = await fetch(client, id)
    c = f["project"]["characters"][0]
    await client.post(
        f"/api/creative/characters/{c['id']}/confirm", json={"expected": c["creative"]["version"], "data": {}}
    )
    f = await fetch(client, id)
    assert not f["scenes"][0]["image_stale"] and f["scenes"][0]["audio_stale"]
    await confirm(client, id, "cast")
    await confirm(client, id, "shots")
    before = len(calls)
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    assert len(calls) == before + 1 and calls[-1][1] == "voice-c"
    # Actual ffmpeg, Fake media. Manifest carries pinned role revisions and segment voices.
    r = await client.post(
        f"/api/projects/{id}/exports", json={"resolution": "720p", "fps": 24, "subtitles": True}
    )
    assert r.status_code == 202, r.text
    await execute_job(r.json()["taskId"])
    out = (await client.get("/api/exports/" + r.json()["exportJobId"])).json()
    assert out["status"] == "done", out
    assert (
        out["settings"]["manifest"]["scenes"][0]["creative"]["audio"]["segments"][0]["voice_id"] == "voice-c"
    )
    assert out["durationSec"] >= 3
    raw = next(v for k, v in env.objects.items() if "/exports/" in k and k.endswith(".mp4"))
    assert len(raw) > 1000
    ass = next(v.decode() for k, v in env.objects.items() if k.endswith(".ass"))
    assert "修改第一句" in ass and "车站恢复了平静" in ass


async def test_old_task_cannot_override_new_edits_and_dedupe(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    body = {"operation": "shot_image", "target": sc["id"]}
    r = await client.post(f"/api/creative/projects/{id}/generate", json=body)
    duplicate = await client.post(f"/api/creative/projects/{id}/generate", json=body)
    assert r.json()["taskId"] == duplicate.json()["taskId"]
    shot = deepcopy(sc["creative"]["shot"])
    shot["action"] = "新的动作"
    changed = await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert changed.status_code == 200, changed.text
    await execute_job(r.json()["taskId"])
    f = await fetch(client, id)
    candidate = next(c for c in f["candidates"] if c["taskId"] == r.json()["taskId"])
    assert candidate["stale"]
    resp = await client.post(
        f"/api/creative/projects/{id}/select",
        json={"candidate_id": candidate["id"], "expected": changed.json()["version"]},
    )
    assert resp.status_code == 409
    assert f["project"]["scenes"][0]["creative"]["shot"]["action"] == "新的动作"
    # Optimistic concurrency protects stale editor saves too.
    assert (
        await client.patch(
            f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
        )
    ).status_code == 409


async def test_legacy_preserved_and_invalid_speaker_rejected(client, monkeypatch):
    old = (
        await client.post(
            "/api/projects", json={"name": "末世信使 · 真实链路验收", "scenes": [{"dialogue": "老人：你好"}]}
        )
    ).json()
    r = await client.post(f"/api/creative/projects/{old['id']}/start")
    assert r.status_code == 200
    sc = r.json()["scenes"][0]
    assert sc["dialogue"] == "老人：你好" and sc["creative"]["needs_binding"]
    assert (await client.get(f"/api/projects/{old['id']}/tasks")).json() == []
    p = await setup(client, monkeypatch)
    sc = p["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["lines"][0]["speaker_id"] = "nonexistent"
    assert (
        await client.patch(
            f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
        )
    ).status_code == 422


async def test_library_pins_copy_and_voice_match_is_real_catalog(client, monkeypatch):
    p = await setup(client, monkeypatch)
    c = p["characters"][0]
    r = await client.post(f"/api/creative/characters/{c['id']}/publish-library")
    assert r.status_code == 200, r.text
    lib = r.json()
    target = (await client.post("/api/projects", json={"name": "复用项目"})).json()
    r = await client.post(f"/api/creative/projects/{target['id']}/reuse/{lib['id']}")
    assert r.status_code == 200, r.text
    imported = r.json()["characters"][0]
    assert imported["image"] != c["image"]
    persona = deepcopy(c["creative"]["persona"])
    persona["appearance"] = "新的外貌"
    await client.patch(
        f"/api/creative/characters/{c['id']}", json={"expected": c["creative"]["version"], "data": persona}
    )
    fresh = (await client.get("/api/projects/" + target["id"])).json()
    assert fresh["characters"][0]["creative"] == imported["creative"]
    assert len((await client.get("/api/creative/library")).json()) == 1


async def test_partial_audio_failure_retry_reuses_paid_segments(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    original = providers().tts.synthesize
    calls = []

    async def fails(text, voice, performance=None):
        calls.append(voice)
        if voice == "voice-b":
            raise RuntimeError("provider interrupted")
        return await original(text, voice, performance)

    monkeypatch.setattr(providers().tts, "synthesize", fails)
    r = await client.post(
        f"/api/creative/projects/{id}/generate", json={"operation": "shot_audio", "target": sc["id"]}
    )
    await execute_job(r.json()["taskId"])
    task = (await client.get("/api/tasks/" + r.json()["taskId"])).json()
    assert task["status"] == "failed"
    monkeypatch.setattr(providers().tts, "synthesize", original)
    retry = await client.post("/api/tasks/" + task["id"] + "/retry")
    assert retry.status_code == 202, retry.text
    spy = AsyncMock(side_effect=original)
    monkeypatch.setattr(providers().tts, "synthesize", spy)
    await execute_job(retry.json()["id"])
    assert spy.await_count == 2


async def test_visual_draft_stales_images_but_not_audio(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    await select(client, id, await generate(client, id, "shot_image", target=sc["id"]))
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    c = p["characters"][0]
    persona = deepcopy(c["creative"]["persona"])
    persona["hair"] = "银色长发"
    r = await client.patch(
        "/api/creative/characters/" + c["id"], json={"expected": c["creative"]["version"], "data": persona}
    )
    assert r.status_code == 200, r.text
    f = await fetch(client, id)
    assert f["scenes"][0]["image_stale"] and not f["scenes"][0]["audio_stale"]
    assert f["project"]["characters"][0]["image"]  # old asset is retained
    assert (await client.post(f"/api/projects/{id}/exports", json={})).status_code == 409


async def test_cancelled_candidate_not_selected_and_refresh_state(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    r = await client.post(
        f"/api/creative/projects/{id}/generate", json={"operation": "shot_image", "target": sc["id"]}
    )
    await client.post("/api/tasks/" + r.json()["taskId"] + "/cancel")
    await execute_job(r.json()["taskId"])
    f = await fetch(client, id)
    assert not any(c["taskId"] == r.json()["taskId"] for c in f["candidates"])
    # T1-E5 explicitly removes the unused response key; readiness owns stage confirmation.
    assert "stage" not in f["project"]["creative"]
    assert f["workflowReadiness"]["shots"] is True
    assert all(c["creative"]["confirmed"] for c in f["project"]["characters"])
    assert len(f["revisions"]) > 5


async def test_removing_last_line_does_not_play_old_audio(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    sc = (await fetch(client, id))["project"]["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["lines"] = []
    shot["narration"] = []
    r = await client.patch(
        "/api/creative/scenes/" + sc["id"], json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert r.status_code == 200, r.text
    assert r.json()["audio"]["segments"] == []
    assert not (await fetch(client, id))["scenes"][0]["audio_stale"]


async def test_matching_and_design_are_distinct_provider_calls(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    c = p["characters"][0]
    tts_provider = providers().tts
    monkeypatch.setattr(
        tts_provider,
        "voices",
        AsyncMock(return_value={"system_voice": [{"voice_id": "voice-a"}]}),
        raising=False,
    )

    async def match(model, instruction, brief):
        assert model is VoiceMatches
        assert brief["catalog"][0]["voice_id"] == "voice-a"
        return VoiceMatches(voice_ids=["voice-a"], reason="预设匹配")

    monkeypatch.setattr(providers().llm, "structured", match)
    await generate(client, id, "voice_match", target=c["id"])
    raw = await tts_provider.synthesize("试听", "voice-a")
    designer = AsyncMock(return_value=("new-designed-voice", raw))
    monkeypatch.setattr(tts_provider, "design", designer, raising=False)
    task = await generate(client, id, "voice_design", target=c["id"])
    designer.assert_awaited_once()
    f = await fetch(client, id)
    candidate = next(x for x in f["candidates"] if x["id"] == task["result"]["candidateId"])
    assert candidate["data"]["mode"] == "design" and candidate["data"]["voice_id"] == "new-designed-voice"


async def test_director_binding_keeps_identity_and_only_invalidates_image(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    await select(client, id, await generate(client, id, "shot_image", target=sc["id"]))
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    sc = (await fetch(client, id))["project"]["scenes"][0]
    director = {
        "template": "车站",
        "objects": [
            {
                "id": "actor",
                "characterId": p["characters"][0]["id"],
                "name": "位置标记",
                "kind": "actor",
                "position": [1, 0, 0],
                "rotation": [0, 0, 0],
                "scale": 1,
                "color": "#ffffff",
            }
        ],
        "keyframes": [],
        "fov": 50,
    }
    r = await client.patch(
        "/api/scenes/" + sc["id"],
        json={"expectedVersion": sc["creative"]["version"], "directorData": director},
    )
    assert r.status_code == 200, r.text
    f = await fetch(client, id)
    assert f["scenes"][0]["image_stale"] and not f["scenes"][0]["audio_stale"]
    assert f["project"]["characters"] == p["characters"]
    assert (
        await client.patch(
            "/api/scenes/" + sc["id"],
            json={"expectedVersion": sc["creative"]["version"], "directorData": director},
        )
    ).status_code == 409


async def test_bgm_upload_and_remix_reuses_all_model_assets(client, monkeypatch):
    p = await setup(client, monkeypatch)
    id = p["id"]
    sc = p["scenes"][0]
    await select(client, id, await generate(client, id, "shot_image", target=sc["id"]))
    await select(client, id, await generate(client, id, "shot_audio", target=sc["id"]))
    raw = await providers().tts.synthesize("音乐测试", "voice")
    uploaded = await client.post(f"/api/projects/{id}/bgm", files={"file": ("music.mp3", raw, "audio/mpeg")})
    assert uploaded.status_code == 201, uploaded.text
    monkeypatch.setattr(
        providers().tts, "synthesize", AsyncMock(side_effect=AssertionError("unexpected paid TTS"))
    )
    monkeypatch.setattr(
        providers().image, "generate", AsyncMock(side_effect=AssertionError("unexpected paid image"))
    )
    for music in [False, True]:
        r = await client.post(
            f"/api/projects/{id}/exports",
            json={"resolution": "720p", "music": music, "bgmAssetId": uploaded.json()["id"]},
        )
        assert r.status_code == 202, r.text
        await execute_job(r.json()["taskId"])
        job = (await client.get("/api/exports/" + r.json()["exportJobId"])).json()
        assert job["status"] == "done", job
    history = (await client.get(f"/api/projects/{id}/exports")).json()
    assert len(history) == 2
    assert history[0]["settings"]["bgm_key"]


async def test_preview_mixes_uploaded_effect_without_model_calls(client, monkeypatch, env):
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    original = p["scenes"][0]
    initial_shot = deepcopy(original["creative"]["shot"])
    initial_shot["duration"] = 3
    for line in initial_shot["lines"] + initial_shot["narration"]:
        line["pause_after"] = 1
    await client.patch(f"/api/creative/scenes/{sid}", json={"expected": original["creative"]["version"], "data": initial_shot})
    await confirm(client, pid, "shots")
    for op in ["shot_image", "shot_audio"]:
        await select(client, pid, await generate(client, pid, op, target=sid))
    raw = await providers().tts.synthesize("effect", "voice")
    upload = await client.post(
        f"/api/projects/{pid}/sound-effects", files={"file": ("bell.mp3", raw, "audio/mpeg")}
    )
    assert upload.status_code == 201, upload.text
    sc = (await fetch(client, pid))["project"]["scenes"][0]
    shot = {
        **sc["creative"]["shot"],
        "sound_effects": [{"asset_id": upload.json()["id"], "start_sec": 0.2, "volume": 0.2}],
    }
    edited = await client.patch(
        f"/api/creative/scenes/{sid}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert edited.status_code == 200, edited.text
    f = await fetch(client, pid)
    assert not f["scenes"][0]["image_stale"] and not f["scenes"][0]["audio_stale"]
    assert f["project"]["scenes"][0]["durationSec"] == sc["durationSec"] > 3
    await confirm(client, pid, "shots")
    for provider, method in [
        (providers().image, "generate"),
        (providers().tts, "synthesize"),
        (providers().video, "create"),
    ]:
        monkeypatch.setattr(
            provider, method, AsyncMock(side_effect=AssertionError("Preview must reuse assets"))
        )
    r = await client.post(
        f"/api/projects/{pid}/preview", json={"resolution": "720p", "fps": 24, "subtitles": True}
    )
    assert r.status_code == 202, r.text
    await execute_job(r.json()["taskId"])
    out = (await client.get("/api/exports/" + r.json()["exportJobId"])).json()
    assert out["status"] == "done", out
    assert out["settings"]["purpose"] == "preview"
    assert abs(out["durationSec"] - sc["durationSec"]) < 0.05
    assert out["settings"]["manifest"]["scenes"][0]["sound_effect_assets"][0]["key"]
    assert (await fetch(client, pid))["project"]["status"] != "已导出"


async def test_old_variant_cannot_follow_new_main_reference(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, c = p["id"], p["characters"][0]
    persona = {**c["creative"]["persona"], "variants": {"侧面": "同一人物侧脸"}}
    await client.patch(
        f"/api/creative/characters/{c['id']}", json={"expected": c["creative"]["version"], "data": persona}
    )
    await select(client, pid, await generate(client, pid, "character_image", target=c["id"], variant="侧面"))
    await select(
        client, pid, await generate(client, pid, "character_image", target=c["id"], nonce="new-main")
    )
    f = await fetch(client, pid)
    c = next(x for x in f["project"]["characters"] if x["id"] == c["id"])
    r = await client.post(
        f"/api/creative/characters/{c['id']}/confirm", json={"expected": c["creative"]["version"], "data": {}}
    )
    assert r.status_code == 200, r.text
    sc = (await fetch(client, pid))["project"]["scenes"][0]
    shot = {**sc["creative"]["shot"], "variants": {c["id"]: "侧面"}}
    r = await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert r.status_code == 200  # Text design may reference a variant before producing it.
    from app.core.db import Session
    from app.models import Scene
    from app.services.creative import shot_inputs
    from app.core.errors import AppError
    import pytest
    async with Session() as db:
        row = await db.get(Scene, sc["id"])
        with pytest.raises(AppError) as error:
            await shot_inputs(db, row, need_audio=False)
        assert error.value.code == "VARIANT_REFERENCE_REQUIRED"


def test_storyboard_model_cannot_invent_sound_assets():
    import pytest
    from pydantic import ValidationError
    from app.schemas.creative import GeneratedShot

    with pytest.raises(ValidationError):
        GeneratedShot(title="虚构音效", location_id="station", sound_effects=[{"asset_id": "invented"}])
