#!/usr/bin/env bash
# Control the AvA Shimejis. Copy next to the Shimeji-ee jar.
# No arguments: toggle. Autostart MUST use --start, never a toggle or raw java.
# --restart clears an existing crowd; --stop is an explicit off switch.
set -u

die() { echo "ERROR: $*" >&2; exit 1; }
notify() { command -v notify-send >/dev/null && notify-send "AvA Shimejis" "$1" || true; }
MODE="${1:---toggle}"
[ "$#" -le 1 ] || die "expected at most one option"
case "$MODE" in
  --start|--stop|--restart|--status|--toggle) ;;
  -h|--help) echo "Usage: $0 [--start|--stop|--restart|--status] (default: toggle)"; exit 0 ;;
  *) die "unknown option: $MODE" ;;
esac

DIR="$(cd "$(dirname "$0")" && pwd -P)"
JAR=""
for candidate in "$DIR/Shimeji-ee.jar" "$DIR/Shimeji.jar" "$DIR"/*himeji*.jar; do
  if [ -f "$candidate" ]; then JAR="$(readlink -f -- "$candidate")"; break; fi
done
[ -n "$JAR" ] || die "no Shimeji jar found in $DIR"
command -v pgrep >/dev/null || die "pgrep not found (install procps-ng on Fedora)"
command -v flock >/dev/null || die "flock not found (install util-linux); refusing to risk duplicate starts"

# Serialize hotkeys, XDG autostart and Hyprland exec-once. Never put a shared,
# predictable lock directly in /tmp, and never unlink an in-use lock file.
umask 077
STATE="${XDG_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}}/ava-shimeji"
mkdir -p "$STATE" || die "cannot create $STATE"
exec 9>"$STATE/control.lock" || die "cannot open the instance-control lock"
flock -w 15 9 || die "another start/stop operation has not finished"
LOG="${XDG_CACHE_HOME:-$HOME/.cache}/ava-shimeji.log"

java_pids() {
  # pgrep's flattened command line cannot distinguish arguments containing
  # spaces, nor resolve `java -jar ./Shimeji-ee.jar`. Inspect NUL-delimited
  # argv and /proc/<pid>/cwd instead. An editor mentioning the jar is NOT Java.
  local pid i jar_path
  local -a argv
  while IFS= read -r pid; do
    argv=()
    mapfile -d '' -t argv 2>/dev/null < "/proc/$pid/cmdline" || continue
    [ "${#argv[@]}" -gt 0 ] || continue
    [ "${argv[0]##*/}" = java ] || continue
    for ((i=1; i < ${#argv[@]} - 1; i++)); do
      [ "${argv[i]}" = -jar ] || continue
      jar_path="${argv[i+1]}"
      case "$jar_path" in /*) ;; *) jar_path="/proc/$pid/cwd/$jar_path" ;; esac
      jar_path="$(readlink -f -- "$jar_path" 2>/dev/null)" || break
      if [ "$jar_path" = "$JAR" ]; then printf '%s\n' "$pid"; fi
      break
    done
  done < <(pgrep -u "$(id -u)" -f '(^|/)java([[:space:]]|$)' 2>/dev/null || true)
}

stop() {
  local -a pids
  local i
  mapfile -t pids < <(java_pids)
  if [ "${#pids[@]}" -eq 0 ]; then echo "Shimejis are not running."; return; fi
  kill -- "${pids[@]}" 2>/dev/null || true
  # Wait for the app's shutdown/settings save before restarting or installing.
  for ((i=0; i<100; i++)); do
    if [ -z "$(java_pids)" ]; then
      notify "Shimejis off"
      echo "Shimejis stopped."
      return 0
    fi
    sleep 0.1
  done
  die "Shimeji-ee did not exit; close it before retrying (no second copy was started)"
}

start() {
  if [ -n "$(java_pids)" ]; then echo "Shimejis are already running (not starting another copy)."; return; fi
  command -v java >/dev/null || die "Java not found - install a full, non-headless JRE"
  mkdir -p "$(dirname "$LOG")" || die "cannot create the log directory"
  cd "$DIR" || die "cannot enter $DIR"
  # Close the control lock in the child; redirect EVERY other fd so a caller
  # capturing our output never waits for the lifetime of the Java process.
  nohup java -jar "$JAR" >>"$LOG" 2>&1 </dev/null 9>&- &
  local app_pid=$! i
  # Keep the lock until nohup has exec'd Java. Without this handshake two
  # simultaneous --start calls can both see 'no Java yet' and start a crowd.
  for ((i=0; i<50; i++)); do
    if java_pids | grep -qx "$app_pid"; then
      disown 2>/dev/null || true
      notify "Shimejis on"
      echo "Shimejis started (pid $app_pid). Log: $LOG"
      return 0
    fi
    if ! kill -0 "$app_pid" 2>/dev/null; then
      wait "$app_pid" 2>/dev/null || true
      die "Java exited during startup; see $LOG"
    fi
    sleep 0.1
  done
  kill "$app_pid" 2>/dev/null || true
  die "Java did not start in time; see $LOG (refusing to start more copies)"
}

case "$MODE" in
  --status) status_pids="$(java_pids)"; [ -n "$status_pids" ] || exit 1; printf '%s\n' "$status_pids" ;;
  --stop) stop ;;
  --start) start ;;
  --restart) stop; start ;;
  --toggle) if [ -n "$(java_pids)" ]; then stop; else start; fi ;;
esac
