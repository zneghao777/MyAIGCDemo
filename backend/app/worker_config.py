"""Portable worker commands: macOS solo pools use separate OS processes."""

import os
import sys


def worker_commands(video_limit=2, *, platform=None, run_id=None):
    platform = platform or sys.platform
    run_id = run_id or str(os.getpid())
    commands = []
    for queue, concurrency in [
        ("script", 2),
        ("image", 2),
        ("tts", 3),
        ("video", video_limit),
        ("compose", 1),
    ]:
        copies = concurrency if platform == "darwin" else 1
        for index in range(copies):
            commands.append(
                [
                    "celery",
                    "-A",
                    "app.worker",
                    "worker",
                    "--pool",
                    "solo" if platform == "darwin" else "prefork",
                    "-Q",
                    "cineai." + queue,
                    "-c",
                    str(1 if platform == "darwin" else concurrency),
                    "-n",
                    f"{queue}-{run_id}-{index + 1}@%h",
                    "-l",
                    "INFO",
                ]
            )
    return commands
