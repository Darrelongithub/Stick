#!/usr/bin/env sh
# Run the AvA runner as a systemd --user service: it starts at login and is
# restarted if it ever dies (Restart=always), so the characters stay up 24/7.
#
#   PYTHON=~/venvs/ava/bin/python ./runner/install-service.sh   # a venv with PySide6
#   ./runner/install-service.sh --uninstall
#
# Hyprland: the user manager only sees WAYLAND_DISPLAY once the session has
# exported it, so the unit retries every few seconds until the desktop is up.
set -eu
UNIT="ava-runner.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ "${1:-}" = "--uninstall" ]; then
  systemctl --user disable --now "$UNIT" 2>/dev/null || true
  rm -f "$UNIT_DIR/$UNIT"
  systemctl --user daemon-reload
  echo "removed $UNIT"
  exit 0
fi

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "no python at $PY" >&2; exit 1; }
"$PY" -c "import PySide6" 2>/dev/null || {
  echo "$PY cannot import PySide6 - set PYTHON to a venv that has it" >&2; exit 1; }

mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/$UNIT" <<UNIT_EOF
[Unit]
Description=AvA Shimejis desktop runner (the four characters)
StartLimitIntervalSec=0

[Service]
ExecStart="$PY" "$REPO/runner/ava_runner.py"
Restart=always
RestartSec=3
# 75 = already running (another copy holds the lock): do not loop on it
RestartPreventExitStatus=75

[Install]
WantedBy=default.target
UNIT_EOF
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT"
echo "installed $UNIT_DIR/$UNIT"
echo "status: systemctl --user status $UNIT"
echo "logs:   journalctl --user -u $UNIT -f"
