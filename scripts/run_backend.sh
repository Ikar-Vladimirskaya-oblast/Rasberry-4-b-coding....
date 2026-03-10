#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$APP_DIR/.venv/bin/python"
CONFIG_FILE="${READERS_CONFIG_PATH:-$APP_DIR/readers.json}"

needs_root_for_addressable_led() {
  "$VENV_PYTHON" - "$CONFIG_FILE" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
if not config_path.exists():
    print("0")
    raise SystemExit(0)

try:
    data = json.loads(config_path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

for reader in data:
    if not reader.get("enabled", True):
        continue
    if not reader.get("led_enabled", False):
        continue
    if str(reader.get("led_mode", "addressable")).lower() == "addressable":
        print("1")
        raise SystemExit(0)

print("0")
PY
}

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv: $VENV_PYTHON"
  echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ "$(needs_root_for_addressable_led)" == "1" && "${EUID}" -ne 0 ]]; then
  echo "Addressable LED mode detected. Restarting backend with sudo."
  exec sudo -E "$VENV_PYTHON" "$APP_DIR/main.py"
fi

exec "$VENV_PYTHON" "$APP_DIR/main.py"
