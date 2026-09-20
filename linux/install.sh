#!/usr/bin/env bash
# Install the AvA 4-pack (Blue/Orange/Yellow/Green) into Shimeji-ee on Linux,
# plus autostart-on-boot and an on/off toggle script.
#
# Usage:
#   ./install.sh [path-to-shimeji-folder] [--replace]
#   --replace : stash any other image sets into img/unused (only the AvA 4 run)
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-}"
REPLACE=false
[ "${2:-}" = "--replace" ] || [ "${1:-}" = "--replace" ] && REPLACE=true

if [ "$TARGET" = "--replace" ]; then TARGET=""; fi
if [ -z "$TARGET" ]; then
  for d in "$HOME/Shimeji-ee" "$HOME/shimeji-ee" "$HOME/Shimeji" "/opt/shimeji-ee" "/opt/Shimeji-ee"; do
    [ -d "$d" ] && TARGET="$d" && break
  done
fi
if [ -z "${TARGET:-}" ] || [ ! -d "$TARGET" ]; then
  echo "Could not find your Shimeji-ee folder. Run: ./install.sh /path/to/shimeji [--replace]"
  exit 1
fi
echo "Shimeji folder: $TARGET"

command -v java >/dev/null || { echo "Java not found - install a JRE first (e.g. sudo apt install default-jre)"; exit 1; }
JAR="$(ls "$TARGET"/Shimeji-ee.jar "$TARGET"/Shimeji.jar "$TARGET"/*himeji*.jar 2>/dev/null | head -n 1)"
[ -n "${JAR:-}" ] || { echo "No Shimeji jar found in $TARGET"; exit 1; }
echo "Found: $JAR"

# 1. image sets (each folder carries its own conf/actions.xml + behaviors.xml)
mkdir -p "$TARGET/img/unused"
for c in Blue Orange Yellow Green; do
  rm -rf "$TARGET/img/$c"
  cp -r "$REPO/AVA Shimejis/$c" "$TARGET/img/$c"
  echo "Installed image set: $c"
done
if $REPLACE; then
  for d in "$TARGET"/img/*/; do
    n="$(basename "$d")"
    case "$n" in Blue|Orange|Yellow|Green|unused) ;; *)
      mv "$d" "$TARGET/img/unused/$n" && echo "Stashed old set: $n -> img/unused" ;;
    esac
  done
fi

# 2. toggle script lives next to the jar (auto-detects its own location)
cp "$REPO/linux/ava-toggle.sh" "$TARGET/ava-toggle.sh"
chmod +x "$TARGET/ava-toggle.sh"
echo "Installed toggle: $TARGET/ava-toggle.sh"

# 3. autostart on boot/login - ALWAYS starts them, even if toggled off earlier
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/ava-shimeji.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=AvA Shimejis
Comment=Start the Animation vs Animator desktop buddies
Exec=bash -c 'cd "$TARGET" && java -jar "$JAR"'
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
echo "Installed autostart: ~/.config/autostart/ava-shimeji.desktop"

echo
echo "Done! Restart Shimeji-ee to meet the crew:"
echo "  \"$TARGET/ava-toggle.sh\"   # stop/start any time"
echo "They will also auto-start on every boot."
echo "Tip: bind ava-toggle.sh to a hotkey in your desktop's Keyboard settings."
