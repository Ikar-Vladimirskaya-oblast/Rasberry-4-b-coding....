#!/usr/bin/env bash
set -euo pipefail

BOOT_CONFIG="/boot/firmware/config.txt"
DEFAULT_BAUDRATE="${I2C_ARM_BAUDRATE:-50000}"
BACKUP_SUFFIX="$(date +%Y%m%d-%H%M%S)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if [[ ! -f "$BOOT_CONFIG" ]]; then
  echo "Missing boot config: $BOOT_CONFIG"
  exit 1
fi

cp "$BOOT_CONFIG" "${BOOT_CONFIG}.bak-${BACKUP_SUFFIX}"

python3 - "$BOOT_CONFIG" "$DEFAULT_BAUDRATE" <<'PY'
from pathlib import Path
import sys

config_path = Path(sys.argv[1])
baudrate = sys.argv[2]
lines = config_path.read_text(encoding="utf-8").splitlines()

required = {
    "dtparam=i2c_arm": "dtparam=i2c_arm=on",
    "dtparam=i2c_arm_baudrate": f"dtparam=i2c_arm_baudrate={baudrate}",
}

seen = {key: False for key in required}
updated: list[str] = []

for raw_line in lines:
    stripped = raw_line.strip()
    replaced = False
    for key, value in required.items():
        if stripped.startswith(f"{key}="):
            updated.append(value)
            seen[key] = True
            replaced = True
            break
    if not replaced:
        updated.append(raw_line)

for key, value in required.items():
    if not seen[key]:
        updated.append(value)

config_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY

echo "Updated $BOOT_CONFIG"
echo "Backup: ${BOOT_CONFIG}.bak-${BACKUP_SUFFIX}"
echo "Current I2C lines:"
grep -nE '^dtparam=i2c_arm(=|_baudrate=)' "$BOOT_CONFIG" || true
echo
echo "Current detected I2C buses:"
i2cdetect -l || true
echo
echo "Reboot is required for baudrate changes to take effect."
