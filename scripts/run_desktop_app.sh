#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_LAUNCHER="$APP_DIR/scripts/run_backend.sh"
DESKTOP_PYTHON="$APP_DIR/.venv/bin/python"
DESKTOP_ENTRYPOINT="$APP_DIR/desktop_app.py"
APP_URL="${DESKTOP_APP_URL:-http://127.0.0.1:8000/}"
STATUS_URL="${DESKTOP_APP_STATUS_URL:-http://127.0.0.1:8000/api/status}"
APP_TITLE="${DESKTOP_APP_TITLE:-RFID Local MVP}"
WINDOW_CLASS="${DESKTOP_APP_CLASS:-rfid-local-mvp}"
ENGINE="${DESKTOP_APP_ENGINE:-chromium}"
CHROMIUM_BIN="${DESKTOP_APP_CHROMIUM_BIN:-}"
LOG_FILE="$APP_DIR/app.log"
CHROMIUM_PROFILE_DIR="$APP_DIR/.cache/chromium-app"

find_chromium() {
  local candidate
  if [[ -n "$CHROMIUM_BIN" && -x "$CHROMIUM_BIN" ]]; then
    printf '%s\n' "$CHROMIUM_BIN"
    return 0
  fi

  for candidate in chromium chromium-browser google-chrome; do
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
    if curl -fsS "$STATUS_URL" >/dev/null 2>&1; then
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

if ! curl -fsS "$STATUS_URL" >/dev/null 2>&1; then
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

run_chromium() {
  local chromium_bin
  chromium_bin="$(find_chromium)"
  mkdir -p "$CHROMIUM_PROFILE_DIR"

  exec "$chromium_bin" \
    --app="$APP_URL" \
    --user-data-dir="$CHROMIUM_PROFILE_DIR" \
    --class="$WINDOW_CLASS" \
    --window-size=1280,800 \
    --disable-gpu \
    --disable-features=UseSkiaRenderer,Vulkan \
    --password-store=basic \
    --use-mock-keychain \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --no-default-browser-check \
    --no-first-run
}

run_pywebview() {
  exec "$DESKTOP_PYTHON" "$DESKTOP_ENTRYPOINT"
}

case "$ENGINE" in
  chromium)
    if find_chromium >/dev/null 2>&1; then
      run_chromium
    fi
    echo "Chromium is not available, falling back to pywebview."
    run_pywebview
    ;;
  pywebview)
    run_pywebview
    ;;
  *)
    echo "Unsupported DESKTOP_APP_ENGINE: $ENGINE"
    echo "Expected: chromium or pywebview"
    exit 1
    ;;
esac
