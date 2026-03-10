#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$APP_DIR/scripts/run_desktop_app.sh"
DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_FILE_NAME="rfid-local-mvp.desktop"

mkdir -p "$DESKTOP_DIR" "$APPLICATIONS_DIR"

create_entry() {
  local target="$1"
  cat >"$target" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=RFID Local MVP
Comment=PN532 test stand for Raspberry Pi
Exec=$LAUNCHER
Path=$APP_DIR
Terminal=false
Categories=Utility;Development;
StartupNotify=true
EOF
  chmod 755 "$target"
}

create_entry "$DESKTOP_DIR/$DESKTOP_FILE_NAME"
create_entry "$APPLICATIONS_DIR/$DESKTOP_FILE_NAME"

echo "Desktop launcher installed:"
echo "  $DESKTOP_DIR/$DESKTOP_FILE_NAME"
echo "  $APPLICATIONS_DIR/$DESKTOP_FILE_NAME"
