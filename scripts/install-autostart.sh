#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/bigstud/Projects/fixed-ops-hub"
PLIST_SRC="$PROJECT_DIR/scripts/com.fixedopshub.streamlit.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.fixedopshub.streamlit.plist"
START_SCRIPT="$PROJECT_DIR/scripts/start-fixed-ops-hub.sh"
OPEN_SCRIPT="$PROJECT_DIR/scripts/open-fixed-ops-hub.sh"
DESKTOP_LINK="$HOME/Desktop/Fixed Ops Hub.command"

chmod +x "$START_SCRIPT" "$OPEN_SCRIPT" "$PROJECT_DIR/scripts/install-autostart.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/fixed-ops-hub"

"$PROJECT_DIR/scripts/create-macos-app.sh"

cp "$PLIST_SRC" "$PLIST_DST"

if launchctl bootout "gui/$(id -u)/com.fixedopshub.streamlit" 2>/dev/null; then
  :
fi

if launchctl bootstrap "gui/$(id -u)" "$PLIST_DST" 2>/dev/null; then
  launchctl enable "gui/$(id -u)/com.fixedopshub.streamlit" 2>/dev/null || true
  launchctl kickstart -k "gui/$(id -u)/com.fixedopshub.streamlit" 2>/dev/null || true
  echo "Login autostart installed."
else
  echo "Login autostart could not be registered automatically."
  echo "Add this app to Login Items instead:"
  echo "  System Settings → General → Login Items → Open at Login"
  echo "  Choose: $HOME/Applications/Fixed Ops Hub.app"
fi

/bin/bash "$OPEN_SCRIPT"

echo "Bookmark: http://localhost:8510"
echo "Desktop shortcut: $DESKTOP_LINK"
