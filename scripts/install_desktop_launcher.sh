#!/bin/zsh
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
app_name="Multi-Agent Trading Intelligence"
app_root="$HOME/Desktop/$app_name.app"
contents_dir="$app_root/Contents"
macos_dir="$contents_dir/MacOS"
resources_dir="$contents_dir/Resources"
launcher_path="$macos_dir/$app_name"
plist_path="$contents_dir/Info.plist"

rm -rf "$app_root"
mkdir -p "$macos_dir" "$resources_dir"

cat > "$launcher_path" <<EOF
#!/bin/zsh
set -euo pipefail
cd "$repo_root"
exec /usr/bin/env python3 -m trading_intelligence.main "\$@"
EOF

chmod +x "$launcher_path"

cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleExecutable</key>
	<string>$app_name</string>
	<key>CFBundleIdentifier</key>
	<string>com.intakt.multi-agent-trading-intelligence</string>
	<key>CFBundleName</key>
	<string>$app_name</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>0.1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>LSMinimumSystemVersion</key>
	<string>12.0</string>
	<key>LSUIElement</key>
	<false/>
</dict>
</plist>
EOF

xattr -dr com.apple.quarantine "$app_root" 2>/dev/null || true
echo "Desktop app created at: $app_root"
