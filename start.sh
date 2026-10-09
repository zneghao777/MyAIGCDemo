#!/usr/bin/env bash
# CineAI 一键启动入口：从任意工作目录调用均可。
set -euo pipefail
CINEAI_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x "$CINEAI_ROOT/backend/.venv/bin/python" ]]; then
  echo '缺少后端环境，请先在项目根目录运行：uv sync --project backend' >&2
  exit 1
fi
exec "$CINEAI_ROOT/backend/.venv/bin/python" "$CINEAI_ROOT/backend/scripts/launch.py" "$@"
