import json
from types import SimpleNamespace

import httpx

from app.core import provider_audit


def test_audit_excludes_response_secrets_and_url_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_audit, "get_settings", lambda: SimpleNamespace(testing=False, local_media_root=tmp_path))
    token = provider_audit.current_task_id.set("task-123")
    try:
        provider_audit.append_call(
            "https://user:password@example.com/v1/images/generations?api_key=secret",
            "image-model", "2026-09-30T00:00:00+00:00", 200,
            httpx.Response(200, json={"id": "call-123", "usage": {"total_tokens": 42, "secret": "private"}, "data": [{"b64_json": "sensitive-media"}], "api_key": "secret"}),
        )
    finally:
        provider_audit.current_task_id.reset(token)
    raw = (tmp_path / "audit/provider-calls.jsonl").read_text()
    row = json.loads(raw)
    assert row["taskId"] == "task-123"
    assert row["usage"] == {"total_tokens": 42}
    assert row["provider"] == "example.com"
    assert all(value not in raw for value in ("password", "secret", "private", "sensitive-media"))


def test_mock_runs_never_write_billing_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_audit, "get_settings", lambda: SimpleNamespace(testing=True, local_media_root=tmp_path))
    provider_audit.append_call("https://example.com/model", "model", "now", 429)
    assert not (tmp_path / "audit").exists()
