#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${RFID_APP_PYTHON_BIN:-python3}"
VENV_DIR="${RFID_APP_VENV_DIR:-$APP_DIR/.venv}"
REQUIREMENTS_FILE="${RFID_APP_REQUIREMENTS_FILE:-$APP_DIR/requirements.txt}"
WHEEL_DIR="${RFID_APP_WHEEL_DIR:-$APP_DIR/vendor/wheels}"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Missing requirements file: $REQUIREMENTS_FILE"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [[ -d "$WHEEL_DIR" ]] && find "$WHEEL_DIR" -mindepth 1 -maxdepth 1 | read -r _; then
  "$VENV_DIR/bin/python" -m pip install --no-index --find-links "$WHEEL_DIR" -r "$REQUIREMENTS_FILE"
  exit 0
fi

"$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"
