#!/usr/bin/env bash
set -euo pipefail

cd /home/alex/organizer_app
export PYTHONPATH="/home/alex/.local/lib/python3.13/site-packages:${PYTHONPATH:-}"

python3 app.py &
app_pid="$!"

cleanup() {
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
  python3 /home/alex/organizer_app/cleanup_hardware.py 2>/dev/null || true
}

trap cleanup TERM INT

started=0
for _ in $(seq 1 35); do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    wait "$app_pid"
    exit $?
  fi
  if curl -fsS --max-time 2 http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
    started=1
    break
  fi
  sleep 1
done

if [ "$started" -ne 1 ]; then
  cleanup
  exit 1
fi

while kill -0 "$app_pid" 2>/dev/null; do
  if ! curl -fsS --max-time 3 http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
    cleanup
    exit 1
  fi
  sleep 10
done

wait "$app_pid"
