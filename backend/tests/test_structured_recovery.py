import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import AppError
from app.providers import deepseek
from app.schemas.creative import Storyboard


async def test_storyboard_keeps_invalid_paid_output_without_charged_retry(monkeypatch, tmp_path):
    settings = SimpleNamespace(testing=False, local_media_root=tmp_path, deepseek_model="deepseek-flash", llm_max_tokens_per_job=12000, deepseek_reasoning_effort="", deepseek_thinking="disabled", deepseek_base_url="https://example.test", deepseek_api_key=SimpleNamespace(get_secret_value=lambda: "private-key"))
    monkeypatch.setattr(deepseek, "get_settings", lambda: settings)
    calls = []

    async def request(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"id": "paid-response", "usage": {"total_tokens": 99}, "choices": [{"finish_reason": "stop", "message": {"content": '{"scenes":[{"title":"可修复草稿"}]}', "reasoning_content": "private-reasoning"}}]})

    monkeypatch.setattr(deepseek, "request", request)
    with pytest.raises(AppError) as caught:
        await deepseek.DeepSeek().structured(Storyboard, "分镜", {})
    assert len(calls) == 1
    assert calls[0]["json"]["thinking"] == {"type": "disabled"}
    assert caught.value.details["rawValue"]["scenes"][0]["title"] == "可修复草稿"
    assert caught.value.details["validationIssues"][0]["loc"]
    path = next((tmp_path / "audit/structured-output").glob("*.json"))
    raw = path.read_text()
    assert json.loads(raw)["responseId"] == "paid-response"
    assert "private-reasoning" not in raw and "private-key" not in raw
    assert path.stat().st_mode & 0o777 == 0o600
