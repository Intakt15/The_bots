#!/bin/zsh
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
desktop_launcher="$HOME/Desktop/Multi-Agent Trading Intelligence.command"

cat > "$desktop_launcher" <<EOF
#!/bin/zsh
set -euo pipefail
cd "$repo_root"
exec /usr/bin/env python3 -m trading_intelligence.main "\$@"
EOF

chmod +x "$desktop_launcher"
echo "Desktop launcher created at: $desktop_launcher"
