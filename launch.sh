#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")"
source .venv/bin/activate
mkdir -p logs
python app.py >> logs/server.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
until curl -sf http://127.0.0.1:8765/api/state >/dev/null; do
  kill -0 $SERVER 2>/dev/null || exit 1
  sleep 0.3
done
chromium --app=http://127.0.0.1:8765 --user-data-dir="$HOME/.cache/studio-profile" --window-size=1500,950