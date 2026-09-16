#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${FIXED_OPS_HUB_PORT:-8510}"
LOG_DIR="${FIXED_OPS_HUB_LOG_DIR:-$HOME/Library/Logs/fixed-ops-hub}"
PID_FILE="$LOG_DIR/streamlit.pid"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    exit 0
  fi
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  exit 0
fi

run_streamlit() {
  exec "$@" run app.py \
    --server.port "$PORT" \
    --server.address localhost \
    --server.headless true
}

if command -v streamlit >/dev/null 2>&1; then
  run_streamlit streamlit
elif python3 -m streamlit --version >/dev/null 2>&1; then
  run_streamlit python3 -m streamlit
elif python -m streamlit --version >/dev/null 2>&1; then
  run_streamlit python -m streamlit
fi

echo "Fixed Ops Hub: streamlit is not installed. Run: pip3 install -r requirements.txt" >&2
exit 1
