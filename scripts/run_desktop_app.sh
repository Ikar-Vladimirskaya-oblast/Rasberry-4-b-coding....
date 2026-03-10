#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$APP_DIR/.venv/bin/python"
LOG_FILE="$APP_DIR/app.log"
APP_URL="http://127.0.0.1:8000/"
PROFILE_DIR="$APP_DIR/.desktop-profile"

find_browser() {
  local candidate
  for candidate in chromium-browser chromium google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

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

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv: $VENV_PYTHON"
  echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "Desktop session is not available. Launch this script from Raspberry Pi desktop."
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:8000/api/status" >/dev/null 2>&1; then
  nohup "$VENV_PYTHON" "$APP_DIR/main.py" >>"$LOG_FILE" 2>&1 &
  if ! wait_for_backend; then
    echo "Backend failed to start. Check $LOG_FILE"
    exit 1
  fi
fi

BROWSER_BIN="$(find_browser || true)"
if [[ -z "$BROWSER_BIN" ]]; then
  echo "Chromium was not found. Install it on Raspberry Pi first."
  exit 1
fi

mkdir -p "$PROFILE_DIR"
exec "$BROWSER_BIN" \
  --app="$APP_URL" \
  --user-data-dir="$PROFILE_DIR" \
  --class=rfid-local-mvp \
  --new-window \
  --window-size=1280,900
