#!/usr/bin/env python3
"""Run API, independent workers, and the durable-outbox scheduler together."""

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("MEDIA_BASE_URL", f"http://127.0.0.1:{os.environ.get('CINEAI_API_PORT', '8000')}/media")
from app.core.config import Settings
from pydantic import ValidationError

try:
    config = Settings()
except ValidationError as exc:
    print("后端配置校验失败：")
    for issue in exc.errors(include_input=False):
        print(" - " + issue["msg"])
    print("请补齐根目录 .env.local 或 .env.example 后重试。")
    raise SystemExit(1)
if config.testing:
    raise SystemExit("dev 启动器禁止 TESTING=true，测试请使用 pytest。")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
runtime = ROOT / ".runtime"
runtime.mkdir(exist_ok=True)
commands = [
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", os.environ.get("CINEAI_API_PORT", "8000")],
    ["celery", "-A", "app.worker", "beat", "--schedule", str(runtime / "celerybeat"), "-l", "INFO"],
]
from app.worker_config import worker_commands

commands.extend(worker_commands(config.video_concurrency_limit))
processes = []


def stop(*args):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    raise SystemExit(0)


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
try:
    for command in commands:
        processes.append(subprocess.Popen([sys.executable, "-m", *command]))
    while all(process.poll() is None for process in processes):
        import time

        time.sleep(1)
finally:
    stop()
