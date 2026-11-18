#!/usr/bin/env bash
# Install the watchdog only. Does not start mascots or enable autostart.
set -euo pipefail
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo 'Python 3 is required; no files changed.' >&2; exit 1; }
scan_status=0
python3 - "$src/shimelinux-manager.py" <<'PYPROC' || scan_status=$?
import os
import sys
from pathlib import Path
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        if entry.stat().st_uid != os.getuid():
            continue
        args = (entry/'cmdline').read_bytes().decode().split('\0')
        old_watcher = any(Path(arg).name == 'shimeji-watchd' for arg in args if arg)
        manager_paths = {str(Path.home()/'.local/lib/stick-shimelinux/manager.py'), sys.argv[1]}
        manager = bool(manager_paths.intersection(args)) and 'run' in args
        engine = (args and Path(args[0]).name == 'java' and '-jar' in args and
                  args[args.index('-jar')+1] == '/usr/share/java/shimelinux.jar')
        if old_watcher or manager or engine:
            raise SystemExit(10)
    except (OSError, ValueError, IndexError, UnicodeError):
        continue
raise SystemExit(0)
PYPROC
if [[ "$scan_status" == 10 ]]; then
  echo 'Stop the existing watchdog and ShimeLinux first; no files changed.' >&2
  exit 1
elif [[ "$scan_status" != 0 ]]; then
  echo 'Could not inspect running processes; refusing installation.' >&2
  exit 1
fi
state="${XDG_STATE_HOME:-$HOME/.local/state}/stick-shimelinux"
mkdir -p "$state" "$HOME/.local/bin" "$HOME/.local/lib/stick-shimelinux"
backup="$(mktemp -d "$state/launcher-backup-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
for name in shimeji shimeji-watchd; do
  if [[ -e "$HOME/.local/bin/$name" ]]; then
    cp -a "$HOME/.local/bin/$name" "$backup/"
  fi
done
install -m 755 "$src/shimelinux-manager.py" "$HOME/.local/lib/stick-shimelinux/manager.py"
cat > "$HOME/.local/bin/shimeji" <<'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.local/lib/stick-shimelinux/manager.py" "${1:-status}"
EOF
cat > "$HOME/.local/bin/shimeji-watchd" <<'EOF'
#!/usr/bin/env bash
# Compatibility entry point: respects the persistent disabled marker.
exec python3 "$HOME/.local/lib/stick-shimelinux/manager.py" run
EOF
chmod 755 "$HOME/.local/bin/shimeji" "$HOME/.local/bin/shimeji-watchd"
# Start disabled. The user must deliberately issue shimeji start after review.
touch "$state/disabled"
printf 'Installed, NOT started. Old launchers saved in: %s\n' "$backup"
echo 'Read docs/shimelinux-watchdog.md before enabling.'
