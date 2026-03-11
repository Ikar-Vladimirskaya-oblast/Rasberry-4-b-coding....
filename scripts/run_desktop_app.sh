#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_LAUNCHER="$APP_DIR/scripts/run_backend.sh"
DESKTOP_PYTHON="$APP_DIR/.venv/bin/python"
DESKTOP_ENTRYPOINT="$APP_DIR/desktop_app.py"
LOG_FILE="$APP_DIR/app.log"

wait_for_backend() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8000/api/status" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if [[ ! -x "$BACKEND_LAUNCHER" || ! -x "$DESKTOP_PYTHON" || ! -f "$DESKTOP_ENTRYPOINT" ]]; then
  echo "Desktop app files are incomplete."
  echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "Desktop session is not available. Launch this script from Raspberry Pi desktop."
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:8000/api/status" >/dev/null 2>&1; then
  if "$BACKEND_LAUNCHER" --needs-root-check; then
    if command -v pkexec >/dev/null 2>&1; then
      pkexec /bin/sh -lc "cd '$APP_DIR' && nohup '$BACKEND_LAUNCHER' --no-escalate >>'$LOG_FILE' 2>&1 &"
    else
      echo "Addressable LED mode requires root. Start backend manually: sudo ./scripts/run_backend.sh"
      exit 1
    fi
  else
    nohup "$BACKEND_LAUNCHER" --no-escalate >>"$LOG_FILE" 2>&1 &
  fi

  if ! wait_for_backend; then
    echo "Backend failed to start. Check $LOG_FILE"
    exit 1
  fi
fi

exec "$DESKTOP_PYTHON" "$DESKTOP_ENTRYPOINT"
