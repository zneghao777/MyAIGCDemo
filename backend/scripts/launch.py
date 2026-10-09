"""Idempotent local launcher; only manages its own supervisor and child groups."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
RUNTIME = ROOT / ".runtime" / "launcher"
STATE = RUNTIME / "state.json"
PYTHON = ROOT / "backend/.venv/bin/python"


def state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def managed(info):
    pid = info.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        return False
    command = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True).stdout
    return str(SCRIPT) in command and "__serve" in command


def save(info):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(info, ensure_ascii=False, indent=2))
    temporary.replace(STATE)


def free_port(preferred):
    for port in range(preferred, min(preferred + 100, 65536)):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("没有可用端口，请设置 CINEAI_WEB_PORT / CINEAI_API_PORT")


def http(url):
    try:
        with build_opener(ProxyHandler({})).open(url, timeout=3) as response:
            return response.status == 200
    except (URLError, TimeoutError, OSError):
        return False


def show(info):
    print(f"工作台：http://127.0.0.1:{info['web_port']}")
    print(f"API 文档：http://127.0.0.1:{info['api_port']}/docs")
    print(f"日志目录：{RUNTIME}")


def stop():
    info = state()
    if not managed(info):
        print("CineAI 一键启动服务未运行。")
        return
    os.kill(info["pid"], signal.SIGTERM)
    for _ in range(100):
        if not managed(info):
            print("CineAI 已停止。")
            return
        time.sleep(0.5)
    raise RuntimeError("CineAI 尚未退出，请检查 launcher.log；未终止其他项目")


def serve(web_port, api_port):
    children = []
    stopping = False

    def on_signal(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    env = {
        **os.environ,
        "CINEAI_API_PORT": str(api_port),
        "NEXT_PUBLIC_API_MODE": "remote",
        "NEXT_PUBLIC_API_BASE_URL": f"http://127.0.0.1:{api_port}",
        "MEDIA_BASE_URL": f"http://127.0.0.1:{api_port}/media",
        "API_CORS_ORIGINS": f"http://127.0.0.1:{web_port},http://localhost:{web_port}",
    }
    commands = [
        ("backend.log", [str(PYTHON), str(ROOT / "backend/scripts/dev.py")]),
        (
            "frontend.log",
            [
                shutil.which("node"),
                str(ROOT / "node_modules/next/dist/bin/next"),
                "dev",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(web_port),
            ],
        ),
    ]
    try:
        for name, command in commands:
            with (RUNTIME / name).open("a") as log:
                children.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                )
        while not stopping and all(p.poll() is None for p in children):
            time.sleep(0.5)
    finally:
        # These groups were created by this supervisor; never kill by port or process name.
        for p in children:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and any(p.poll() is None for p in children):
            time.sleep(0.25)
        for p in children:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
        print("CineAI 子进程已退出。", flush=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "__serve":
        serve(int(sys.argv[2]), int(sys.argv[3]))
        return
    parser = argparse.ArgumentParser(description="CineAI 一键启动（不启动或停止共享数据库）")
    parser.add_argument("action", nargs="?", choices=["start", "restart", "stop", "status"], default="start")
    parser.add_argument("--open", action="store_true", help="启动完成后打开工作台")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "control.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action in ("restart", "stop"):
            stop()
            if args.action == "stop":
                return
        info = state()
        if args.action == "status":
            if not managed(info):
                print("CineAI 一键启动服务未运行。")
                return
            show(info)
            print("前端：", "可访问" if http(f"http://127.0.0.1:{info['web_port']}") else "未就绪")
            print(
                "后端：", "可访问" if http(f"http://127.0.0.1:{info['api_port']}/openapi.json") else "未就绪"
            )
            return
        if not managed(info):
            if not shutil.which("node") or not (ROOT / "node_modules/next/dist/bin/next").exists():
                raise RuntimeError("缺少前端依赖，请安装 Node.js 并在项目根目录运行 npm ci")
            subprocess.run([str(PYTHON), str(ROOT / "backend/scripts/check_config.py")], cwd=ROOT, check=True)
            web_port = free_port(int(os.environ.get("CINEAI_WEB_PORT", "3000")))
            api_port = free_port(int(os.environ.get("CINEAI_API_PORT", "8001")))
            if web_port == api_port:
                api_port = free_port(api_port + 1)
            with (RUNTIME / "launcher.log").open("a") as log:
                process = subprocess.Popen(
                    [str(PYTHON), str(SCRIPT), "__serve", str(web_port), str(api_port)],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            info = {"pid": process.pid, "web_port": web_port, "api_port": api_port}
            save(info)
            print("正在启动 API、Worker、Beat 和前端…", flush=True)
        else:
            print("CineAI 已启动，复用现有进程。", flush=True)
        for _ in range(90):
            if not managed(info):
                raise RuntimeError(f"启动进程已退出，请查看 {RUNTIME}")
            if http(f"http://127.0.0.1:{info['api_port']}/openapi.json") and http(
                f"http://127.0.0.1:{info['web_port']}"
            ):
                show(info)
                if args.open:
                    import webbrowser

                    webbrowser.open(f"http://127.0.0.1:{info['web_port']}")
                return
            time.sleep(1)
        stop()
        raise RuntimeError(f"等待启动超时，已停止本次服务，请查看 {RUNTIME}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        sys.exit(1)
