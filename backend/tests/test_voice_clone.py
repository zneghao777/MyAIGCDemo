import io
import wave
from unittest.mock import AsyncMock

import httpx
import pytest
from test_creative import fetch, generate, select, setup

from app.core.errors import AppError
from app.providers import providers
from app.providers.minimax import MiniMaxTTS


def wav(seconds):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * int(seconds * 16000))
    return stream.getvalue()


async def test_clone_provider_reuses_voice_and_propagates_rejection(monkeypatch):
    tts = MiniMaxTTS()
    monkeypatch.setattr(tts, "voices", AsyncMock(return_value={"voice_cloning": [{"voice_id": "existing"}]}))
    call = AsyncMock()
    monkeypatch.setattr("app.providers.minimax.request", call)
    assert await tts.clone(b"input", "existing") == "existing"
    call.assert_not_awaited()
    monkeypatch.setattr(tts, "voices", AsyncMock(return_value={}))
    calls = []

    async def request(method, url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/files/upload"):
            assert kwargs["data"]["purpose"] == "voice_clone"
            return httpx.Response(200, json={"file": {"file_id": 42}})
        assert kwargs["json"]["file_id"] == 42
        assert kwargs["json"]["need_noise_reduction"]
        return httpx.Response(200, json={"base_resp": {"status_code": 2013}})

    monkeypatch.setattr("app.providers.minimax.request", request)
    with pytest.raises(AppError) as error:
        await tts.clone(b"input", "newVoice")
    assert error.value.code == "VOICE_CLONE_UNAVAILABLE"
    assert len(calls) == 2


async def test_reference_upload_clone_and_new_reference_invalidates_candidate(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, cid = p["id"], p["characters"][0]["id"]

    async def upload(seconds):
        f = await fetch(client, pid)
        c = next(c for c in f["project"]["characters"] if c["id"] == cid)
        return await client.post(
            f"/api/creative/characters/{cid}/voice-reference",
            data={"expected": c["creative"]["version"]},
            files={"file": ("reference.wav", wav(seconds), "audio/wav")},
        )

    assert (await upload(1)).status_code == 422
    response = await upload(12)
    assert response.status_code == 200, response.text
    clone = AsyncMock(return_value="fixed-cloned-voice")
    monkeypatch.setattr(providers().tts, "clone", clone, raising=False)
    task = await generate(client, pid, "voice_clone", target=cid, text="全部去死吧。")
    selected = await select(client, pid, task)
    ch = next(c for c in selected["characters"] if c["id"] == cid)
    assert ch["creative"]["voice"]["mode"] == "clone"
    assert ch["creative"]["voice"]["voice_id"] == "fixed-cloned-voice"
    assert ch["creative"]["voice"]["reference"]["asset_id"]
    clone.assert_awaited_once()
    assert (await upload(13)).status_code == 200
    candidate = next(
        c for c in (await fetch(client, pid))["candidates"] if c["id"] == task["result"]["candidateId"]
    )
    assert candidate["stale"]
    # Replacing a sample does not silently replace the already selected voice.
    assert candidate["selected"]


async def test_original_dialogue_binding_and_missing_recordings_never_call_tts(client, monkeypatch):
    from test_creative import confirm

    p = await setup(client, monkeypatch)
    pid, cid = p["id"], p["characters"][0]["id"]
    f = await fetch(client, pid)
    c = next(c for c in f["project"]["characters"] if c["id"] == cid)
    response = await client.post(
        f"/api/creative/characters/{cid}/voice-source",
        data={"expected": c["creative"]["version"]},
        files={"file": ("original.wav", wav(1), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    await select(client, pid, {"result": response.json()})
    f = await fetch(client, pid)
    c = next(c for c in f["project"]["characters"] if c["id"] == cid)
    response = await client.post(
        f"/api/creative/characters/{cid}/confirm", json={"expected": c["creative"]["version"], "data": {}}
    )
    assert response.status_code == 200
    await confirm(client, pid, "cast")
    await confirm(client, pid, "shots")
    f = await fetch(client, pid)
    sc = f["project"]["scenes"][0]
    response = await client.post(
        f"/api/creative/projects/{pid}/generate", json={"operation": "shot_audio", "target": sc["id"]}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "SOURCE_AUDIO_REQUIRED"

    async def upload(line_id):
        sc = (await fetch(client, pid))["project"]["scenes"][0]
        return await client.post(
            f"/api/creative/scenes/{sc['id']}/line-audio",
            data={"expected": sc["creative"]["version"], "line_id": line_id},
            files={"file": ("line.wav", wav(1), "audio/wav")},
        )

    assert (await upload("not-in-this-scene")).status_code == 422
    assert (await upload("line-0")).status_code == 200
    assert (await fetch(client, pid))["scenes"][0]["audio_stale"]
    for line_id in ["line-1", "narrator"]:
        assert (await upload(line_id)).status_code == 200
    f = await fetch(client, pid)
    assert not f["scenes"][0]["audio_stale"]
    assert all(s["strategy"] == "source-audio-v1" for s in f["scenes"][0]["segments"])
