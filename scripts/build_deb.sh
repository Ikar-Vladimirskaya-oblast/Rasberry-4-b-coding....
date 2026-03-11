#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="rfid-local-mvp"
VERSION="0.1.0"
OUTPUT_DIR="$APP_DIR/dist"
BUILD_ROOT="$APP_DIR/build/deb"
BUNDLE_WHEELS=1

usage() {
  cat <<'EOF'
Usage: scripts/build_deb.sh [--version <version>] [--output <dir>] [--no-bundle-wheels]

Builds a Debian package for Raspberry Pi OS.

Options:
  --version <version>    Package version, default: 0.1.0
  --output <dir>         Output directory, default: ./dist
  --no-bundle-wheels     Do not pre-download Python wheels into the package
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --no-bundle-wheels)
      BUNDLE_WHEELS=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb is required to build a .deb package."
  exit 1
fi

ARCH="$(dpkg --print-architecture)"
PKG_DIR="$BUILD_ROOT/${PACKAGE_NAME}_${VERSION}_${ARCH}"
APP_INSTALL_DIR="$PKG_DIR/opt/$PACKAGE_NAME"
DEBIAN_DIR="$PKG_DIR/DEBIAN"
ETC_DIR="$PKG_DIR/etc/$PACKAGE_NAME"
ICON_DIR="$PKG_DIR/usr/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$PKG_DIR/usr/share/applications"
SYSTEMD_DIR="$PKG_DIR/lib/systemd/system"
BIN_DIR="$PKG_DIR/usr/bin"
WHEEL_DIR="$APP_INSTALL_DIR/vendor/wheels"

rm -rf "$PKG_DIR"
mkdir -p \
  "$APP_INSTALL_DIR" \
  "$DEBIAN_DIR" \
  "$ETC_DIR" \
  "$ICON_DIR" \
  "$DESKTOP_DIR" \
  "$SYSTEMD_DIR" \
  "$BIN_DIR" \
  "$WHEEL_DIR" \
  "$PKG_DIR/var/lib/$PACKAGE_NAME"

tar \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude="build" \
  --exclude="dist" \
  --exclude=".runtime" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  -C "$APP_DIR" \
  -cf - . | tar -C "$APP_INSTALL_DIR" -xf -

cp "$APP_DIR/readers.json" "$ETC_DIR/readers.json"
cp "$APP_DIR/packaging/deb/rfid-local-mvp.service" "$SYSTEMD_DIR/rfid-local-mvp.service"
cp "$APP_DIR/packaging/deb/rfid-local-mvp.desktop" "$DESKTOP_DIR/rfid-local-mvp.desktop"
cp "$APP_DIR/packaging/deb/rfid-local-mvp.svg" "$ICON_DIR/rfid-local-mvp.svg"
cp "$APP_DIR/packaging/deb/postinst" "$DEBIAN_DIR/postinst"
cp "$APP_DIR/packaging/deb/prerm" "$DEBIAN_DIR/prerm"
cp "$APP_DIR/packaging/deb/postrm" "$DEBIAN_DIR/postrm"

cat >"$BIN_DIR/rfid-local-mvp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

export READERS_CONFIG_PATH="/etc/rfid-local-mvp/readers.json"
export DATABASE_PATH="/var/lib/rfid-local-mvp/events.db"
export DESKTOP_APP_ENGINE="${DESKTOP_APP_ENGINE:-chromium}"

exec /opt/rfid-local-mvp/scripts/run_desktop_app.sh "$@"
EOF

cat >"$BIN_DIR/rfid-local-mvp-backend" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

export READERS_CONFIG_PATH="/etc/rfid-local-mvp/readers.json"
export DATABASE_PATH="/var/lib/rfid-local-mvp/events.db"

exec /opt/rfid-local-mvp/scripts/run_backend.sh --no-escalate "$@"
EOF

cat >"$DEBIAN_DIR/control" <<EOF
Package: $PACKAGE_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Ikar Vladimirskaya oblast
Depends: bash, curl, python3, python3-dev, python3-pip, python3-smbus, python3-venv, python3-gi, gir1.2-webkit2-4.1, chromium, i2c-tools, libgpiod3, python3-libgpiod, sudo
Description: Local RFID PN532 test stand for Raspberry Pi
 FastAPI backend, realtime GUI, SQLite log storage and desktop launcher
 for PN532 reader testing on Raspberry Pi.
EOF

cat >"$DEBIAN_DIR/conffiles" <<'EOF'
/etc/rfid-local-mvp/readers.json
EOF

chmod 755 \
  "$BIN_DIR/rfid-local-mvp" \
  "$BIN_DIR/rfid-local-mvp-backend" \
  "$DEBIAN_DIR/postinst" \
  "$DEBIAN_DIR/prerm" \
  "$DEBIAN_DIR/postrm" \
  "$APP_INSTALL_DIR/scripts/"*.sh

if [[ "$BUNDLE_WHEELS" -eq 1 ]]; then
  DOWNLOAD_PYTHON=""
  if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
    DOWNLOAD_PYTHON="$APP_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    DOWNLOAD_PYTHON="$(command -v python3)"
  fi

  if [[ -n "$DOWNLOAD_PYTHON" ]]; then
    "$DOWNLOAD_PYTHON" -m pip download --dest "$WHEEL_DIR" -r "$APP_DIR/requirements.txt"
  else
    echo "Skipping wheel download: no Python interpreter with pip is available."
  fi
fi

mkdir -p "$OUTPUT_DIR"
dpkg-deb --root-owner-group --build "$PKG_DIR" "$OUTPUT_DIR/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo "Built package: $OUTPUT_DIR/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
