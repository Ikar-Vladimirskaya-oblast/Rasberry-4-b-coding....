#!/usr/bin/env bash
set -euo pipefail

URL="http://127.0.0.1:5000"

for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if command -v chromium-browser >/dev/null 2>&1; then
  exec chromium-browser --app="$URL" --start-maximized --noerrdialogs --disable-infobars
fi

if command -v chromium >/dev/null 2>&1; then
  exec chromium --app="$URL" --start-maximized --noerrdialogs --disable-infobars
fi

if command -v xdg-open >/dev/null 2>&1; then
  exec xdg-open "$URL"
fi

echo "No browser found. Open $URL manually."
