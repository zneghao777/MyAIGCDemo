import base64
import io
import math
import struct
import wave
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, TransientProviderError
from app.providers import providers
from app.providers.mimo import MiMoTTS, resolve_voice


def wav():
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(
            b"".join(
                struct.pack("<h", int(10000 * math.sin(i * 2 * math.pi * 440 / 24000))) for i in range(24000)
            )
        )
    return out.getvalue()


@pytest.fixture
def mimo(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "mimo")
    monkeypatch.setattr(settings, "mimo_api_key", SecretStr("test-key"))
    monkeypatch.setattr(providers(), "tts", MiMoTTS())
    return providers().tts


async def test_mimo_request_keeps_script_separate_from_directions(mimo, monkeypatch):
    raw = wav()

    async def request(method, url, **kwargs):
        assert method == "POST" and url == "https://api.xiaomimimo.com/v1/chat/completions"
        assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
        assert kwargs["retries"] == 0
        body = kwargs["json"]
        assert body["model"] == "mimo-v2.5-tts"
        assert body["audio"] == {"format": "wav", "voice": "白桦"}
        assert body["messages"][1] == {"role": "assistant", "content": "别走。\n等我！"}
        assert "悲伤" in body["messages"][0]["content"]
        assert "0.9" in body["messages"][0]["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"audio": {"data": base64.b64encode(raw).decode()}}}]}
        )

    monkeypatch.setattr("app.providers.mimo.request", request)
    assert (
        await mimo.synthesize("别走。\n等我！", "白桦", {"speed": 0.9, "pitch": -1, "emotion": "sad"}) == raw
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"audio": {"data": "???"}}}]},
        {"choices": [{"message": {"audio": {"data": ""}}}]},
        {"choices": [{"message": {"audio": {"data": "bm90IGF1ZGlv"}}}]},
    ],
)
async def test_mimo_rejects_missing_or_invalid_audio(mimo, monkeypatch, payload):
    monkeypatch.setattr(
        "app.providers.mimo.request", AsyncMock(return_value=httpx.Response(200, json=payload))
    )
    with pytest.raises(AppError) as exc:
        await mimo.synthesize("台词", "白桦")
    assert exc.value.code == "PROVIDER_OUTPUT_INVALID"


async def test_mimo_rejects_old_custom_voice_and_model_without_request(mimo, monkeypatch):
    request = AsyncMock()
    monkeypatch.setattr("app.providers.mimo.request", request)
    for voice, performance in [("old-cloned-voice", {}), ("白桦", {"model": "speech-2.8-hd"})]:
        with pytest.raises(AppError) as exc:
            await mimo.synthesize("台词", voice, performance)
        assert exc.value.code == "VOICE_RESELECTION_REQUIRED"
    request.assert_not_awaited()
    assert resolve_voice("male-qn-qingse") == "白桦"


async def test_mimo_propagates_transient_failure(mimo, monkeypatch):
    monkeypatch.setattr(
        "app.providers.mimo.request",
        AsyncMock(side_effect=TransientProviderError("PROVIDER_TIMEOUT", "超时", 504)),
    )
    with pytest.raises(TransientProviderError):
        await mimo.synthesize("台词", "白桦")


@pytest.mark.parametrize("text", ["台词", "这是一段较长的台词。" * 8])
async def test_mimo_wav_runs_through_existing_mp3_pipeline(mimo, monkeypatch, text):
    from app.services.tts import synthesize

    monkeypatch.setattr(mimo, "synthesize", AsyncMock(return_value=wav()))
    monkeypatch.setattr(get_settings(), "tts_max_chars", 50)
    raw, duration = await synthesize(text, "白桦", AsyncMock())
    assert duration >= 900 and raw.startswith(b"ID3")


def test_mimo_credentials_do_not_require_minimax(monkeypatch):
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("TTS_PROVIDER", "mimo")
    values = {
        "_env_file": None,
        "database_url": "sqlite:///test.db",
        "deepseek_api_key": "test",
        "image_api_key": "test",
        "mimo_api_key": "test",
        "minimax_api_key": "",
        "feature_video_generation": False,
    }
    assert Settings(**values).tts_model == "mimo-v2.5-tts"
    with pytest.raises(ValidationError):
        Settings(**{**values, "mimo_api_key": ""})
    with pytest.raises(ValidationError):
        Settings(**{**values, "feature_video_generation": True})


async def test_switch_preserves_old_audio_and_blocks_unsupported_jobs(client, monkeypatch):
    from test_creative import fetch, generate, select, setup

    p = await setup(client, monkeypatch)
    pid, sid, cid = p["id"], p["scenes"][0]["id"], p["characters"][0]["id"]
    await select(client, pid, await generate(client, pid, "shot_audio", target=sid))
    previous = (await fetch(client, pid))["scenes"][0]["segments"]
    monkeypatch.setattr(get_settings(), "tts_provider", "mimo")
    f = await fetch(client, pid)
    assert f["scenes"][0]["audio_stale"]
    assert f["scenes"][0]["segments"] == previous
    assert (
        f["capabilities"]["voiceDesign"]
        and f["capabilities"]["voiceClone"]
        and not f["capabilities"]["roleAudio"]
    )
    voices = (await client.get("/api/tts/voices")).json()
    assert "白桦" in {v["voiceId"] for v in voices}
    for operation in ("role_audio",):
        response = await client.post(
            f"/api/creative/projects/{pid}/generate", json={"operation": operation, "target": cid}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "TTS_CAPABILITY_UNSUPPORTED"
    response = await client.post(
        f"/api/creative/projects/{pid}/generate", json={"operation": "shot_audio", "target": sid}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "VOICE_RESELECTION_REQUIRED"
    # Explicit preview and selection upgrades one role; no silent migration of old takes.
    task = await generate(client, pid, "voice_preview", target=cid, voice_id="白桦", text="你好。")
    updated = await select(client, pid, task)
    voice = next(c for c in updated["characters"] if c["id"] == cid)["creative"]["voice"]
    assert voice["provider"] == "mimo" and voice["model"] == "mimo-v2.5-tts" and voice["voice_id"] == "白桦"


async def test_design_and_clone_use_distinct_models_and_unchanged_text(mimo, monkeypatch):
    from app.providers.mimo import reference_voice_id

    calls = []

    async def request(*args, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200, json={"choices": [{"message": {"audio": {"data": base64.b64encode(wav()).decode()}}}]}
        )

    monkeypatch.setattr("app.providers.mimo.request", request)
    _, raw = await mimo.design("温柔沉稳的成年女声", "不要修改这句台词。", "unused")
    assert calls[0]["model"] == "mimo-v2.5-tts-voicedesign"
    assert calls[0]["audio"] == {"format": "wav", "optimize_text_preview": False}
    assert calls[0]["messages"][1]["content"] == "不要修改这句台词。"
    await mimo.synthesize(
        "第二句台词。", reference_voice_id(raw), {"model": "mimo-v2.5-tts-voiceclone", "reference_audio": raw}
    )
    assert calls[1]["model"] == "mimo-v2.5-tts-voiceclone"
    assert calls[1]["audio"]["voice"].startswith("data:audio/wav;base64,")
    assert base64.b64decode(calls[1]["audio"]["voice"].split(",", 1)[1]) == raw
    assert calls[1]["messages"][1]["content"] == "第二句台词。"


async def test_clone_rejects_missing_mismatched_and_oversize_reference(mimo, monkeypatch):

    request = AsyncMock()
    monkeypatch.setattr("app.providers.mimo.request", request)
    for raw, voice, code in [
        (None, "missing", "VOICE_REFERENCE_REQUIRED"),
        (wav(), "wrong-identity", "VOICE_REFERENCE_MISMATCH"),
        (b"ID3" + bytes(7_500_000), "large", "VOICE_REFERENCE_TOO_LARGE"),
    ]:
        with pytest.raises(AppError) as error:
            await mimo.synthesize(
                "台词", voice, {"model": "mimo-v2.5-tts-voiceclone", "reference_audio": raw}
            )
        assert error.value.code == code
    request.assert_not_awaited()


async def test_design_selection_pins_sample_across_lines_and_library(client, monkeypatch, env):
    from test_creative import confirm, fetch, generate, select, setup

    from app.providers.mimo import reference_voice_id

    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    monkeypatch.setattr(get_settings(), "tts_provider", "mimo")
    monkeypatch.setattr(providers(), "tts", MiMoTTS())
    calls = []

    async def request(*args, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200, json={"choices": [{"message": {"audio": {"data": base64.b64encode(wav()).decode()}}}]}
        )

    monkeypatch.setattr("app.providers.mimo.request", request)
    cid = p["characters"][0]["id"]
    task = await generate(client, pid, "voice_design", target=cid, text="初次见面。")
    before = (await fetch(client, pid))["project"]["characters"][0]["creative"]["voice"]
    assert before["provider"] == "minimax"  # Generating a candidate never selects it.
    await select(client, pid, task)
    for c in p["characters"]:
        if c["id"] != cid:
            await select(
                client, pid, await generate(client, pid, "voice_preview", target=c["id"], voice_id="苏打")
            )
        ch = next(x for x in (await fetch(client, pid))["project"]["characters"] if x["id"] == c["id"])
        response = await client.post(
            f"/api/creative/characters/{c['id']}/confirm",
            json={"expected": ch["creative"]["version"], "data": {}},
        )
        assert response.status_code == 200, response.text
    f = await fetch(client, pid)
    voice = next(c for c in f["project"]["characters"] if c["id"] == cid)["creative"]["voice"]
    reference = voice["reference"]
    sample = env.objects[reference["key"]]
    assert voice["model"] == "mimo-v2.5-tts-voiceclone"
    assert voice["generation_model"] == "mimo-v2.5-tts-voicedesign"
    assert voice["voice_id"] == reference_voice_id(sample)
    response = await client.patch(
        f"/api/creative/projects/{pid}/narrator",
        json={"expected": f["project"]["creative"]["version"], "data": {"voice_id": "白桦", "speed": 1}},
    )
    assert response.status_code == 200
    await confirm(client, pid, "cast")
    await confirm(client, pid, "shots")
    await select(client, pid, await generate(client, pid, "shot_audio", target=sid))
    f = await fetch(client, pid)
    segment = next(x for x in f["scenes"][0]["segments"] if x["line"]["speaker_id"] == cid)
    assert segment["reference"]["asset_id"] == reference["asset_id"]
    assert segment["model"] == "mimo-v2.5-tts-voiceclone"
    clone_call = next(x for x in calls if x["model"] == "mimo-v2.5-tts-voiceclone")
    assert base64.b64decode(clone_call["audio"]["voice"].split(",", 1)[1]) == sample
    assert sum(x["model"] == "mimo-v2.5-tts-voicedesign" for x in calls) == 1
    # Uploading a new reference must not modify the already selected sample.
    ch = next(x for x in f["project"]["characters"] if x["id"] == cid)
    upload = await client.post(
        f"/api/creative/characters/{cid}/voice-reference",
        data={"expected": ch["creative"]["version"]},
        files={"file": ("other.wav", repeated_wav(12), "audio/wav")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["voice"]["reference"]["key"] == reference["key"]
    # A fresh audition of the selected voice clones the pinned sample, never redesigns it.
    await generate(client, pid, "voice_preview", target=cid, voice_id=voice["voice_id"], text="换一句话。")
    assert calls[-1]["model"] == "mimo-v2.5-tts-voiceclone"
    assert base64.b64decode(calls[-1]["audio"]["voice"].split(",", 1)[1]) == sample
    library = await client.post(f"/api/creative/characters/{cid}/publish-library")
    assert library.status_code == 200, library.text
    library_ref = library.json()["data"]["voice"]["reference"]
    assert library_ref["key"].startswith("library/") and env.objects[library_ref["key"]] == sample
    other = (await client.post("/api/projects", json={"name": "复用验收"})).json()
    await client.post(f"/api/creative/projects/{other['id']}/start")
    reused = await client.post(f"/api/creative/projects/{other['id']}/reuse/{library.json()['id']}")
    assert reused.status_code == 200, reused.text
    imported = reused.json()["characters"][0]["creative"]["voice"]
    assert imported["reference"]["key"] != reference["key"]
    assert imported["reference"]["key"] != library_ref["key"]
    assert env.objects[imported["reference"]["key"]] == sample
    assert imported["voice_id"] == voice["voice_id"]


def repeated_wav(seconds):
    out = io.BytesIO()
    with wave.open(io.BytesIO(wav()), "rb") as src:
        frames = src.readframes(src.getnframes())
    with wave.open(out, "wb") as dest:
        dest.setnchannels(1)
        dest.setsampwidth(2)
        dest.setframerate(24000)
        dest.writeframes(frames * seconds)
    return out.getvalue()


async def test_uploaded_clone_candidate_keeps_its_own_reference(client, monkeypatch, env):
    from test_creative import fetch, generate, select, setup

    p = await setup(client, monkeypatch)
    pid, cid = p["id"], p["characters"][0]["id"]
    monkeypatch.setattr(get_settings(), "tts_provider", "mimo")
    monkeypatch.setattr(providers(), "tts", MiMoTTS())
    calls = []

    async def request(*args, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200, json={"choices": [{"message": {"audio": {"data": base64.b64encode(wav()).decode()}}}]}
        )

    monkeypatch.setattr("app.providers.mimo.request", request)

    async def upload(seconds):
        c = next(x for x in (await fetch(client, pid))["project"]["characters"] if x["id"] == cid)
        return await client.post(
            f"/api/creative/characters/{cid}/voice-reference",
            data={"expected": c["creative"]["version"]},
            files={"file": ("ref.wav", repeated_wav(seconds), "audio/wav")},
        )

    assert (await upload(12)).status_code == 200
    task = await generate(client, pid, "voice_clone", target=cid, text="参考音色的试听。")
    await select(client, pid, task)
    f = await fetch(client, pid)
    selected_voice = next(c for c in f["project"]["characters"] if c["id"] == cid)["creative"]["voice"]
    assert selected_voice["reference"]["origin"] == "upload"
    assert calls[0]["model"] == "mimo-v2.5-tts-voiceclone"
    assert (
        base64.b64decode(calls[0]["audio"]["voice"].split(",", 1)[1])
        == env.objects[selected_voice["reference"]["key"]]
    )
    assert (await upload(13)).status_code == 200
    f = await fetch(client, pid)
    assert next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])["stale"]
    assert (
        next(c for c in f["project"]["characters"] if c["id"] == cid)["creative"]["voice"] == selected_voice
    )
