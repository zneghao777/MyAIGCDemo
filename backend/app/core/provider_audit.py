"""Local billing evidence without credentials, prompts, or media."""

import fcntl
import json
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core.config import get_settings

current_task_id: ContextVar[str | None] = ContextVar("provider_task_id", default=None)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def append_call(url, model, started_at, status, response=None, error_type=None):
    settings = get_settings()
    if settings.testing or not model:
        return
    parsed = urlsplit(url)
    data = {}
    if response is not None:
        try:
            data = response.json()
        except (ValueError, TypeError):
            pass
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    usage = {k: v for k, v in usage.items() if isinstance(v, (int, float, bool))} if isinstance(usage, dict) else {}
    row = {
        "taskId": current_task_id.get(),
        "provider": parsed.hostname,
        "path": parsed.path,
        "model": model,
        "startedAt": started_at,
        "finishedAt": timestamp(),
        "httpStatus": status,
        "usage": usage,
        "errorType": error_type,
    }
    if isinstance(data, dict):
        for key in ("id", "task_id"):
            value = data.get(key)
            if isinstance(value, str) and len(value) <= 128:
                row["responseId" if key == "id" else "providerTaskId"] = value
    folder = settings.local_media_root / "audit"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "provider-calls.jsonl").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_UN)
