#!/usr/bin/env bash
# Toggle the AvA Shimejis on/off.
# Install: copy this file into your Shimeji-ee folder, then run it (or bind it to a hotkey).
# Boot behavior is handled separately by ava-shimeji.desktop (autostart) which
# ALWAYS starts the Shimejis on login - so even if you toggled them off and
# forgot, they're back after a reboot.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$(ls "$DIR"/Shimeji-ee.jar "$DIR"/Shimeji.jar "$DIR"/*himeji*.jar 2>/dev/null | head -n 1)"
LOG="$HOME/.cache/ava-shimeji.log"

notify() { command -v notify-send >/dev/null && notify-send "AvA Shimejis" "$1" || true; }

if [ -z "${JAR:-}" ]; then
  echo "No Shimeji jar found in $DIR" >&2; exit 1
fi

if pgrep -f "$JAR" >/dev/null; then
  pkill -f "$JAR"
  notify "Shimejis off (back on next boot)"
  echo "Shimejis stopped."
else
  mkdir -p "$(dirname "$LOG")"
  cd "$DIR" && nohup java -jar "$JAR" >>"$LOG" 2>&1 &
  disown
  notify "Shimejis on"
  echo "Shimejis started."
fi
