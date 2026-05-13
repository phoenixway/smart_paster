#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.local/bin"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cat > "$HOME/.local/bin/smart-paster" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SMART_PASTER_HOME="\${SMART_PASTER_HOME:-$SCRIPT_DIR}"
exec python3 "\$SMART_PASTER_HOME/run_smart_paster.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/smart-paster"
echo "Installed: $HOME/.local/bin/smart-paster"
echo "Make sure ~/.local/bin is in PATH."
