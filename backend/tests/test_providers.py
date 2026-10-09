import base64
import io
import httpx
import pytest
from PIL import Image
from app.providers.deepseek import DeepSeek
from app.providers.gpt_image import GPTImage
from app.providers.minimax import MiniMaxTTS
from app.schemas import TextResult
from app.core.errors import AppError, TransientProviderError
from app.services.tts import split_text


async def test_llm_repairs_invalid_schema(monkeypatch):
    calls = []

    async def request(*args, **kwargs):
        calls.append(kwargs)
        content = '{"bad":1}' if len(calls) == 1 else '{"text":"修复成功"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr("app.providers.deepseek.request", request)
    result = await DeepSeek().structured(TextResult, "JSON", {})
    assert result.text == "修复成功" and len(calls) == 2


async def test_image_reference_failure_never_degrades_to_text(monkeypatch):
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        raise AppError("PROVIDER_ERROR", "不支持", 502, {"status": 415})

    monkeypatch.setattr("app.providers.gpt_image.request", request)
    with pytest.raises(AppError) as error:
        await GPTImage().generate("角色", "16:9", "low", [b"image"])
    assert error.value.code == "REFERENCE_UNSUPPORTED"
    assert len(calls) == 1 and calls[0].endswith("edits")


async def test_image_normalizes_output_and_preserves_all_references(monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (16, 16)).save(output, format="JPEG")

    async def request(method, url, **kwargs):
        assert len(kwargs["files"]) == 2
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(output.getvalue()).decode()}]}
        )

    monkeypatch.setattr("app.providers.gpt_image.request", request)
    raw, logs = await GPTImage().generate("两人", "16:9", "low", [output.getvalue()] * 2)
    assert raw.startswith(b"\x89PNG") and not logs


async def test_minimax_hex_and_business_error(monkeypatch):
    async def request(*args, **kwargs):
        assert kwargs["json"]["output_format"] == "hex"
        return httpx.Response(
            200, json={"base_resp": {"status_code": 0}, "data": {"audio": b"ID3test".hex()}}
        )

    monkeypatch.setattr("app.providers.minimax.request", request)
    assert await MiniMaxTTS().synthesize("台词", "voice") == b"ID3test"

    async def failure(*args, **kwargs):
        return httpx.Response(200, json={"base_resp": {"status_code": 1002}})

    monkeypatch.setattr("app.providers.minimax.request", failure)
    with pytest.raises(TransientProviderError):
        await MiniMaxTTS().synthesize("台词", "voice")


def test_long_tts_split_preserves_text():
    text = ("你好。欢迎来到这个世界！" * 700) + "结尾"
    pieces = split_text(text, 2000)
    assert "".join(pieces) == text and all(len(p) <= 2000 for p in pieces)


async def test_minimax_alignment_requests_timestamps_and_pins_voice(monkeypatch):
    async def request(*args, **kwargs):
        body = kwargs["json"]
        assert body["subtitle_enable"] and body["subtitle_type"] == "word"
        assert body["model"] == "speech-2.8-hd"
        assert body["voice_setting"] == {
            "voice_id": "locked",
            "speed": 0.9,
            "pitch": -1,
            "emotion": "calm",
            "vol": 1,
        }
        return httpx.Response(
            200, json={"data": {"audio": b"ID3test".hex(), "subtitle_file": "https://example.test/subtitles"}}
        )

    monkeypatch.setattr("app.providers.minimax.request", request)
    audio, subtitles = await MiniMaxTTS().synthesize_aligned(
        "台词", "locked", {"model": "speech-2.8-hd", "speed": 0.9, "pitch": -1, "emotion": "calm"}
    )
    assert audio == b"ID3test" and subtitles == {"url": "https://example.test/subtitles"}
