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
source_path="/tmp/multi-agent-trading-intelligence-launcher.swift"
log_dir="$HOME/Library/Logs/Multi-Agent Trading Intelligence"
log_file="$log_dir/launcher.log"

rm -rf "$app_root"
mkdir -p "$macos_dir" "$resources_dir" "$log_dir"
rm -f "$source_path"

cat > "$source_path" <<EOF
import AppKit
import Foundation

final class LauncherDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        let repoRoot = "$repo_root"
        let logDir = "$log_dir"
        let logFile = "$log_file"
        let fileManager = FileManager.default
        try? fileManager.createDirectory(atPath: logDir, withIntermediateDirectories: true)

        let shell = Process()
        shell.executableURL = URL(fileURLWithPath: "/bin/zsh")
        shell.arguments = [
            "-lc",
            "cd \"\(repoRoot)\" && nohup /usr/bin/env python3 -m trading_intelligence.main >> \"\(logFile)\" 2>&1 &"
        ]

        do {
            try shell.run()
            shell.waitUntilExit()
        } catch {
            let message = "Failed to launch trading bot: \(error)\n"
            try? message.write(toFile: logFile, atomically: true, encoding: .utf8)
        }

        NSApp.terminate(nil)
    }
}

@main
struct LauncherMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = LauncherDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.prohibited)
        app.run()
    }
}
EOF

swiftc -parse-as-library -framework AppKit "$source_path" -o "$launcher_path"
rm -f "$source_path"

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
