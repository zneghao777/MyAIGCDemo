"""Validate configuration without printing credentials."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import ValidationError
from app.core.config import Settings

try:
    s = Settings()
    print("配置校验通过；连接可用性需启动后检查 /api/health。")
except ValidationError as exc:
    for issue in exc.errors(include_input=False):
        print(issue["msg"])
    raise SystemExit(1)
