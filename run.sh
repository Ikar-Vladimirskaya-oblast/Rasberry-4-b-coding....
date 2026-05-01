#!/usr/bin/env bash
set -euo pipefail

cd /home/alex/organizer_app
export PYTHONPATH="/home/alex/.local/lib/python3.13/site-packages:${PYTHONPATH:-}"
exec python3 app.py
