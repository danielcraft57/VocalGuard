#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"
HOST="${TELEPHONY_BIND_HOST:-127.0.0.1}"
PORT="${TELEPHONY_BIND_PORT:-8090}"
exec python -m uvicorn backend.telephony_daemon.main:app --host "$HOST" --port "$PORT"
