#!/bin/bash
set -euo pipefail

APP_DIR="/Users/bigstud/Projects/fixed-ops-hub"
PORT="${FIXED_OPS_HUB_PORT:-8510}"
LOG_DIR="$HOME/Library/Logs/fixed-ops-hub"
PID_FILE="$LOG_DIR/streamlit.pid"
STREAMLIT="/Users/bigstud/Library/Python/3.9/bin/streamlit"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    exit 0
  fi
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  exit 0
fi

exec "$STREAMLIT" run app.py \
  --server.port "$PORT" \
  --server.address localhost \
  --server.headless true
