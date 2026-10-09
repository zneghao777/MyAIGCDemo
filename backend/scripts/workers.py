"""Production worker launcher; one unique solo process per slot on macOS."""

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from app.core.config import get_settings
from app.worker_config import worker_commands

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
    for command in worker_commands(get_settings().video_concurrency_limit):
        processes.append(subprocess.Popen([sys.executable, "-m", *command]))
    import time
    while all(process.poll() is None for process in processes):
        time.sleep(1)
finally:
    stop()
