#!/bin/bash
set -euo pipefail

PORT="${FIXED_OPS_HUB_PORT:-8510}"
URL="http://localhost:${PORT}"
START_SCRIPT="/Users/bigstud/Projects/fixed-ops-hub/scripts/start-fixed-ops-hub.sh"

_streamlit_healthy() {
  curl -sf "${URL}/_stcore/health" >/dev/null 2>&1
}

if ! _streamlit_healthy; then
  FIXED_OPS_HUB_PORT="$PORT" /bin/bash "$START_SCRIPT" >/dev/null 2>&1 &
  for _ in $(seq 1 40); do
    if _streamlit_healthy; then
      break
    fi
    sleep 0.25
  done
fi

CHROME_APP="/Applications/Google Chrome.app"

if [[ -d "$CHROME_APP" ]]; then
  open -a "$CHROME_APP" "$URL"
else
  open "$URL"
fi
