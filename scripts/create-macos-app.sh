#!/bin/bash
set -euo pipefail

APP_NAME="Fixed Ops Hub"
APP_DIR="$HOME/Applications/${APP_NAME}.app"
PROJECT_DIR="/Users/bigstud/Projects/fixed-ops-hub"
OPEN_SCRIPT="$PROJECT_DIR/scripts/open-fixed-ops-hub.sh"

mkdir -p "$APP_DIR/Contents/MacOS"

cat > "$APP_DIR/Contents/MacOS/${APP_NAME}" <<EOF
#!/bin/bash
exec /bin/bash "$OPEN_SCRIPT"
EOF

chmod +x "$APP_DIR/Contents/MacOS/${APP_NAME}"

cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.fixedopshub.app</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

ln -sf "$OPEN_SCRIPT" "$HOME/Desktop/Fixed Ops Hub.command"
chmod +x "$HOME/Desktop/Fixed Ops Hub.command"

echo "Created: $APP_DIR"
echo "Desktop shortcut: $HOME/Desktop/Fixed Ops Hub.command"
echo "Bookmark: http://localhost:8510"
