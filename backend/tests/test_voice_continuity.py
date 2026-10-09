from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
from app.core.errors import AppError
from app.providers import providers
from app.services.voice_continuity import align_lines
from test_creative import setup, fetch, select, generate, confirm


def test_alignment_refuses_mismatched_or_crossed_subtitles():
    words = [{"text": "你好。", "start": 0, "end": 300}, {"text": "回家！", "start": 500, "end": 800}]
    assert align_lines(["你好", "回家"], words, 1000) == [(0, 400.0), (420, 1000)]
    with pytest.raises(AppError):
        align_lines(["你好", "走吧"], words, 1000)
    with pytest.raises(AppError):
        align_lines(["你好", "回家"], [{"text": "你好回家", "start": 0, "end": 800}], 1000)
    with pytest.raises(AppError):
        align_lines(["你好", "回家"], [words[0], {**words[1], "start": 200}], 1000)


async def test_stable_role_take_replaces_only_role_and_rejects_stale(client, monkeypatch):
    from app.core.config import get_settings

    p = await setup(client, monkeypatch)
    pid, scene, role = p["id"], p["scenes"][0], p["characters"][0]
    await select(client, pid, await generate(client, pid, "shot_audio", target=scene["id"]))
    before = (await fetch(client, pid))["scenes"][0]["segments"]
    pinned = role["creative"]["voice"]["model"]
    monkeypatch.setattr(get_settings(), "minimax_tts_model", "changed-default")
    request = await client.post(
        f"/api/creative/projects/{pid}/estimate", json={"operation": "role_audio", "target": role["id"]}
    )
    assert request.status_code == 200 and request.json()["calls"] == 1
    aligned = AsyncMock(return_value=(providers().tts.raw, [{"text": "第1句", "start": 0, "end": 500}]))
    monkeypatch.setattr(providers().tts, "synthesize_aligned", aligned, raising=False)
    task = await generate(client, pid, "role_audio", target=role["id"])
    assert aligned.await_args.args[2] == {"model": pinned, "speed": 1, "emotion": "calm", "pitch": 0}
    monkeypatch.setattr(get_settings(), "minimax_tts_model", pinned)
    await select(client, pid, task)
    after = (await fetch(client, pid))["scenes"][0]["segments"]
    assert after[0]["key"] != before[0]["key"]
    assert after[0]["strategy"] == "role-continuous-v1"
    assert [x["key"] for x in after[1:]] == [x["key"] for x in before[1:]]
    assert not (await fetch(client, pid))["scenes"][0]["audio_stale"]
    task = await generate(client, pid, "role_audio", target=role["id"], nonce="second")
    f = await fetch(client, pid)
    sc = f["project"]["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["lines"][0]["text"] = "已经修改了台词"
    await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    r = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={"candidate_id": task["result"]["candidateId"], "expected": role["creative"]["version"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_CANDIDATE"


async def test_stable_speed_and_image_independence(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, sc = p["id"], p["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["lines"][0].update(speed=0.5, emotion="angry")
    await client.patch(
        f"/api/creative/scenes/{sc['id']}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    await confirm(client, pid, "shots")
    spy = AsyncMock(wraps=providers().tts.synthesize)
    monkeypatch.setattr(providers().tts, "synthesize", spy)
    await select(client, pid, await generate(client, pid, "shot_audio", target=sc["id"]))
    assert spy.await_args_list[0].args[2]["speed"] == 1
    assert spy.await_args_list[0].args[2]["emotion"] == "calm"
    from app.services.creative import image_fingerprint

    persona = p["characters"][0]["creative"]["persona"]
    assert image_fingerprint(persona, "test") == image_fingerprint(
        {**persona, "voice_mode": "expressive", "base_pitch": 2}, "test"
    )


def test_minimax_nested_word_timestamps():
    subtitles = [
        {
            "text": "你好。回家。",
            "time_begin": 0,
            "time_end": 900,
            "timestamped_words": [
                {"word": "你好", "time_begin": 20, "time_end": 300},
                {"word": "。", "time_begin": 300, "time_end": 400},
                {"word": "回家", "time_begin": 600, "time_end": 800},
            ],
        }
    ]
    assert align_lines(["你好。", "回家。"], subtitles, 1000) == [(0, 420), (520, 1000)]


async def test_alignment_retry_reuses_paid_recording_across_task_ids(client, monkeypatch):
    from app.tasks.execute import execute_job

    p = await setup(client, monkeypatch)
    pid, role = p["id"], p["characters"][0]
    aligned = AsyncMock(return_value=(providers().tts.raw, {"url": "https://example.test/subtitles"}))
    monkeypatch.setattr(providers().tts, "synthesize_aligned", aligned, raising=False)
    download = AsyncMock(side_effect=AppError("TEMPORARY", "模拟字幕下载失败", 422))
    monkeypatch.setattr("app.providers.minimax.fetch_subtitles", download)
    r = await client.post(
        f"/api/creative/projects/{pid}/generate",
        json={"operation": "role_audio", "target": role["id"], "nonce": "retry-test"},
    )
    tid = r.json()["taskId"]
    await execute_job(tid)
    assert (await client.get("/api/tasks/" + tid)).json()["status"] == "failed"
    monkeypatch.setattr(
        "app.providers.minimax.fetch_subtitles",
        AsyncMock(return_value=[{"text": "第1句", "start": 0, "end": 500}]),
    )
    r = await client.post("/api/tasks/" + tid + "/retry")
    assert r.status_code == 202, r.text
    new_id = r.json()["id"]
    assert new_id != tid
    await execute_job(new_id)
    assert (await client.get("/api/tasks/" + new_id)).json()["status"] == "done"
    assert aligned.await_count == 1
