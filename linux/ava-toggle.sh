#!/usr/bin/env bash
# Toggle the AvA Shimejis on/off.
# Install: copy this file into your Shimeji-ee folder, then run it (or bind it to a hotkey).
# Boot behavior is handled separately by ava-shimeji.desktop (autostart) which
# ALWAYS starts the Shimejis on login - so even if you toggled them off and
# forgot, they're back after a reboot.
set -u

die() { echo "ERROR: $*" >&2; exit 1; }

DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$(ls "$DIR"/Shimeji-ee.jar "$DIR"/Shimeji.jar "$DIR"/*himeji*.jar 2>/dev/null | head -n 1)"
LOG="$HOME/.cache/ava-shimeji.log"

notify() { command -v notify-send >/dev/null && notify-send "AvA Shimejis" "$1" || true; }

if [ -z "${JAR:-}" ]; then
  echo "No Shimeji jar found in $DIR" >&2; exit 1
fi

# pgrep/pkill match an EXTENDED REGEX, not a literal string. A jar path is not
# one: "Shimeji (1)" - the name most archive tools give a re-extraction, so
# the common case - never matched, instances stacked up and could never be
# stopped again. Escape every ERE metacharacter, then scope the pattern to an
# actual `java -jar <this jar>` command line so an editor, archive tool or
# indexer that merely has the jar open is never signalled.
command -v pgrep >/dev/null && command -v pkill >/dev/null || die \
  "pgrep/pkill not found (install procps) - cannot tell whether the Shimejis are already running, so refusing to start more"
ere_escape() { printf '%s' "$1" | sed -e 's/[][\^$.|?*+(){}\\]/\\&/g'; }
JAR_RE="$(ere_escape "$JAR")"
PATTERN="(^|/)java[[:space:]].*-jar[[:space:]]+${JAR_RE}([[:space:]]|\$)"

if PIDS="$(pgrep -f -- "$PATTERN" 2>/dev/null)" && [ -n "$PIDS" ]; then
  COUNT="$(printf '%s\n' "$PIDS" | wc -l | tr -d ' ')"
  pkill -f -- "$PATTERN" 2>/dev/null || true
  notify "Shimejis off (back on next boot)"
  echo "Shimejis stopped ($COUNT process$( [ "$COUNT" = 1 ] || echo es ))."
else
  mkdir -p "$(dirname "$LOG")" || die "cannot create $(dirname "$LOG")"
  cd "$DIR" || die "cannot enter $DIR"
  # Background ONLY the java command, with every fd redirected. Backgrounding
  # a compound list (`cd ... && nohup java ... &`) parks a subshell that keeps
  # the CALLER's stdout/stderr open for as long as the app lives, so piped
  # callers - hotkey daemons, CI jobs - block forever waiting for EOF.
  nohup java -jar "$JAR" >>"$LOG" 2>&1 </dev/null &
  APP_PID=$!
  disown 2>/dev/null || true
  notify "Shimejis on"
  echo "Shimejis started (pid $APP_PID). Log: $LOG"
fi
