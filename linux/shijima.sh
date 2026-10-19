#!/usr/bin/env bash
# Use this same pack with Shijima-Qt (the React/Qt shimeji runner) instead of
# Shimeji-ee - including autostart, which is the thing Shijima-Qt cannot do on
# its own under Hyprland (and which is why it never came back after a reboot).
#
# Shijima-Qt loads a mascot from a folder named <Name>.mascot containing
# actions.xml, behaviors.xml and img/ - a different layout from Shimeji-ee's
# conf/ + loose PNGs.  This script builds that layout out of the repo and
# either packages it for Shijima-Qt's own import dialog (a .zip, the supported
# way) or drops it into Shijima-Qt's mascots folder directly.
#
# Every action type the pack uses is implemented by libshijima, so the pack
# loads as-is.
#
# Usage:
#   ./linux/shijima.sh                 # build + package (nothing is installed)
#   ./linux/shijima.sh --install       # also copy into Shijima-Qt's mascots/
#   ./linux/shijima.sh --autostart     # start it with the session (Hyprland/sway)
#   ./linux/shijima.sh --install --autostart --restart  # repair a running crew
#   ./linux/shijima.sh --syntax v2     # override detection: auto|v1|v2|v3|lua
#   ./linux/shijima.sh --check         # report what is where
#   ./linux/shijima.sh --uninstall     # remove what --install/--autostart added
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/linux/hyprland-common.sh"
OUT="${SHIJIMA_BUILD_DIR:-$REPO/build/shijima}"
HYPR_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
RULES_CONF="$HYPR_DIR/ava-shijima-qt.conf"
XDG_AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/ava-shijima-qt.desktop"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ava-shimeji"
SESSION_HELPER_PATH="$DATA_DIR/shijima-session.sh"
MASCOTS_URL="http://127.0.0.1:32456/shijima/api/v1/mascots"

MODE="build"
DO_AUTOSTART=false
DO_RESTART=false
SYNTAX=auto
RULES_FILE=""
SESSION_HELPER=""

die() { echo "ERROR: $*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --install)   MODE="install" ;;
    --autostart) DO_AUTOSTART=true ;;
    --restart)   DO_RESTART=true; MODE=install ;;
    --syntax)    shift; [ $# -gt 0 ] || die "--syntax needs a value"; SYNTAX="$1" ;;
    --syntax=*)  SYNTAX="${1#*=}" ;;
    --check)     MODE="check" ;;
    --uninstall) MODE="uninstall" ;;
    --out)       shift; [ $# -gt 0 ] || die "--out needs a path"; OUT="$1" ;;
    --out=*)     OUT="${1#*=}" ;;
    -h|--help)   sed -n '2,/^set -u$/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           die "unknown option: $1" ;;
  esac
  shift
done
case "$SYNTAX" in auto|v1|v2|v3|lua) ;; *) die "--syntax must be auto, v1, v2, v3 or lua" ;; esac

# ---------------------------------------------------------------- locations
is_flatpak_install() {
  # Match the launcher we will actually use when both installs exist.
  command -v shijima-qt >/dev/null 2>&1 && return 1
  [ -d "$HOME/.var/app/com.pixelomer.ShijimaQt" ] \
    || [ -d "$HOME/.var/app/com.pixelomer.ShijimaQt.Qt" ] \
    || { command -v flatpak >/dev/null 2>&1 \
         && flatpak list --app 2>/dev/null | grep -qi 'com.pixelomer.ShijimaQt'; }
}

mascot_dirs() {
  # native and Flatpak locations, in the order Qt would check them for the
  # install type we can see (Flatpak keeps its data in ~/.var/app)
  local native="${XDG_DATA_HOME:-$HOME/.local/share}/Shijima-Qt/mascots"
  local flat="$HOME/.var/app/com.pixelomer.ShijimaQt/data/Shijima-Qt/mascots"
  local flat2="$HOME/.var/app/com.pixelomer.ShijimaQt.Qt/data/Shijima-Qt/mascots"
  # If a launcher is installed, do not accidentally update the stale data of
  # the *other* install type (native vs Flatpak).
  local launcher; launcher="$(launcher_cmd)"
  case "$launcher" in
    shijima-qt) printf '%s\n' "$native"; return ;;
    *' com.pixelomer.ShijimaQt.Qt') printf '%s\n' "$flat2"; return ;;
    *' com.pixelomer.ShijimaQt') printf '%s\n' "$flat"; return ;;
  esac
  if is_flatpak_install; then
    printf '%s\n' "$flat" "$flat2" "$native" "$HOME/.local/share/shijima-qt/mascots"
  else
    printf '%s\n' "$native" "$flat" "$flat2" "$HOME/.local/share/shijima-qt/mascots"
  fi
}

first_existing_mascot_dir() {
  local d
  while IFS= read -r d; do
    [ -d "$d" ] && { printf '%s' "$d"; return 0; }
    [ -d "$(dirname "$d")" ] && { printf '%s' "$d"; return 0; }
  done < <(mascot_dirs)
  return 1
}

# ---------------------------------------------------------------- build
build() {
  command -v python3 >/dev/null || die "python3 is required"
  local chars="Blue Orange Yellow Green" char src dest
  [ -n "$OUT" ] && [ "$OUT" != "/" ] || die "refusing an empty or root build folder"
  # --out and SHIJIMA_BUILD_DIR can point anywhere, so only clear a folder that
  # is empty or that a previous build marked as its own.
  if [ -d "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && [ ! -f "$OUT/.ava-shijima-build" ]; then
    die "refusing to clear $OUT: it is not a previous build folder. Pick an empty folder with --out."
  fi
  rm -rf "$OUT"
  mkdir -p "$OUT" || die "cannot create $OUT"
  : > "$OUT/.ava-shijima-build"
  for char in $chars; do
    src="$REPO/AVA Shimejis/$char"
    [ -d "$src" ] || die "missing image set $src"
    [ -f "$src/conf/actions.xml" ] || die "$src/conf/actions.xml is missing"
    dest="$OUT/$char.mascot"
    mkdir -p "$dest/img" || die "cannot create $dest"
    cp "$src/conf/actions.xml" "$dest/actions.xml" || die "cannot copy actions.xml"
    cp "$src/conf/behaviors.xml" "$dest/behaviors.xml" || die "cannot copy behaviors.xml"
    cp "$src"/*.png "$dest/img/" 2>/dev/null || die "no frames found in $src"
    note "$char.mascot  ($(find "$dest/img" -name '*.png' -printf . | wc -c | tr -d ' ') frames)"
    # Shijima-Qt resolves every <Pose Image="..."> against <mascot>/img, and it
    # lowercases the name before it looks it up - catch a broken folder here
    # instead of with an invisible mascot.
    python3 - "$dest" <<'PY' || die "$char.mascot would not load in Shijima-Qt"
import os, re, sys
dest = sys.argv[1]
root = os.path.join(dest, "img")
have = set(os.listdir(root))
bad = []
for xml in ("actions.xml", "behaviors.xml"):
    text = open(os.path.join(dest, xml), encoding="utf-8-sig", errors="surrogateescape").read()
    for name in re.findall(r'Image="([^"]+)"', text):
        base = name.lstrip("/")
        if base.lower() not in have:
            bad.append(base)
if bad:
    print("  missing image(s) referenced by actions.xml: %s" % ", ".join(sorted(set(bad))[:5]))
    sys.exit(1)
PY
    if command -v zip >/dev/null 2>&1; then
      ( cd "$OUT" && zip -qr "$char.mascot.zip" "$char.mascot" ) \
        || die "cannot zip $char.mascot"
    fi
  done
  if command -v zip >/dev/null 2>&1; then
    note "also packaged: $OUT/<Character>.mascot.zip  (Shijima-Qt's import dialog takes these)"
  else
    note "install 'zip' to also get .mascot.zip archives for the import dialog"
  fi
}

# ---------------------------------------------------------------- install
install_mascots() {
  local dir; dir="$(first_existing_mascot_dir || true)"
  if [ -z "${dir:-}" ]; then
    dir="$(mascot_dirs | head -n 1)"
    note "Shijima-Qt has not created its mascots folder here yet, so it is being"
    note "created now: $dir"
    note "(run Shijima-Qt once and re-run with --check if it disagrees; Flatpak"
    note " installs keep theirs under ~/.var/app/)"
  fi
  mkdir -p "$dir" || die "cannot create $dir"
  local char
  for char in Blue Orange Yellow Green; do
    if [ -e "$dir/$char.mascot" ]; then
      # never delete somebody else's import - move it aside like install.sh does
      mv "$dir/$char.mascot" "$dir/$char.mascot.old-$$" || die "cannot replace $char.mascot"
      note "kept the previous $char.mascot as $char.mascot.old-$$"
    fi
    cp -r "$OUT/$char.mascot" "$dir/$char.mascot" || die "cannot copy $char.mascot"
    note "installed $dir/$char.mascot"
  done
  note "(Shijima-Qt's own README asks you to prefer its import dialog:"
  note " drop $OUT/*.mascot.zip onto the app instead if you have trouble.)"
}

# QSettings uses the organization/application names, not the mascots path.
settings_file() {
  local dir; dir="$(first_existing_mascot_dir || mascot_dirs | head -n 1)"
  case "$dir" in
    "$HOME/.var/app/"*) printf '%s/config/pixelomer/Shijima-Qt.conf' "${dir%%/data/*}" ;;
    *) printf '%s/pixelomer/Shijima-Qt.conf' "${XDG_CONFIG_HOME:-$HOME/.config}" ;;
  esac
}

shijima_running() {
  pgrep -u "$(id -u)" -x 'shijima-qt|Shijima-Qt' >/dev/null 2>&1 && return 0
  # AppImage / other executable names: don't overwrite a running app's data.
  python3 - <<'PY_RUNNING'
import socket, sys
try:
    with socket.create_connection(("127.0.0.1", 32456), timeout=0.3):
        pass
except OSError:
    sys.exit(1)
PY_RUNNING
}

prepare_install() {
  if shijima_running; then
    $DO_RESTART || die "quit Shijima-Qt first, or use --install --autostart --restart; running apps keep the OLD breeding XML in memory"
    # Exact process names and our UID only, never a broad pkill -f shijima.
    pkill -u "$(id -u)" -x 'shijima-qt|Shijima-Qt' 2>/dev/null || true
    local i
    for ((i=0; i<50; i++)); do
      shijima_running || break
      sleep 0.2
    done
    shijima_running && die "Shijima-Qt is still running; quit it from its menu and retry"
  fi
  return 0
}

# ---------------------------------------------------------------- hyprland
# Same detection logic as linux/hyprland.sh, but for Shijima-Qt's own windows
# (class/title contains "shijima") instead of Shimeji-ee's java windows.
RULES_LUA="$HYPR_DIR/ava-shijima.lua"
CLASS_REGEX='.*[Ss]hijima.*'

hypr_present() {
  [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && return 0
  case "${XDG_CURRENT_DESKTOP:-}" in *[Hh]yprland*) return 0 ;; esac
  [ -f "$HYPR_DIR/hyprland.conf" ] || [ -f "$HYPR_DIR/hyprland.lua" ]
}

hypr_flavour() {
  if [ "$SYNTAX" != auto ]; then printf '%s' "$SYNTAX"; return; fi
  hypr_syntax "$HYPR_DIR"
}

rules_text() { hypr_rules "$1" "$CLASS_REGEX" ava-shijima-qt false; }
lua_rules_text() { rules_text lua; }

launcher_cmd() {
  if command -v shijima-qt >/dev/null 2>&1; then printf 'shijima-qt'; return; fi
  if command -v flatpak >/dev/null 2>&1; then
    local id installed
    installed="$(flatpak list --app --columns=application 2>/dev/null)"
    for id in com.pixelomer.ShijimaQt com.pixelomer.ShijimaQt.Qt; do
      if printf '%s\n' "$installed" | grep -qxF "$id"; then
        printf 'flatpak run --env=QT_QPA_PLATFORM=xcb %s' "$id"
        return
      fi
    done
  fi
  printf ''
}

# Keep the session logic in a testable Python module; the wrapper contains
# only the installed path and launcher. It uses the live API, not pgrep, to
# avoid duplicate starts/spawns, and removes only excess AvA mascots.
write_session_helper() {
  local launcher="$1"
  SESSION_HELPER="$SESSION_HELPER_PATH"
  mkdir -p "$DATA_DIR" || die "cannot create $DATA_DIR"
  cp "$REPO/linux/shijima-session.py" "$DATA_DIR/shijima-session.py" || die "cannot install the session helper"
  {
    printf '#!/usr/bin/env sh\n# Managed by linux/shijima.sh\n'
    printf 'exec python3 %s -- %s\n' "$(shell_quote "$DATA_DIR/shijima-session.py")" "$launcher"
  } > "$SESSION_HELPER" || die "cannot write $SESSION_HELPER"
  chmod +x "$SESSION_HELPER" || die "cannot make $SESSION_HELPER executable"
  note "wrote $SESSION_HELPER"
}

write_rules() {
  if ! hypr_present; then
    note "not a Hyprland session - no window rules needed (other desktops do not"
    note "tile the mascot windows).  Autostart goes through XDG instead, below."
    RULES_FILE=""
    return 0
  fi
  if grep -qF "$SESSION_HELPER_PATH" "$RULES_CONF" "$RULES_LUA" 2>/dev/null; then
    DO_AUTOSTART=true
  fi
  local flavour; flavour="$(hypr_flavour)"
  [ "$flavour" != unknown ] || die "cannot detect Hyprland version; run in your desktop session or pass --syntax v2 (0.30-0.52), v3 (0.53+) or lua"
  mkdir -p "$HYPR_DIR" || die "cannot create $HYPR_DIR"
  if [ "$flavour" = lua ]; then
    [ -f "$HYPR_DIR/hyprland.lua" ] || die "no $HYPR_DIR/hyprland.lua to include the rules from"
  else
    [ -f "$HYPR_DIR/hyprland.conf" ] || die "no $HYPR_DIR/hyprland.conf; add a source for $RULES_CONF to your custom config"
  fi
  case "$flavour" in
    lua)
      printf '%s\n' "$(lua_rules_text)" > "$RULES_LUA" || die "cannot write $RULES_LUA"
      note "wrote $RULES_LUA"
      if grep -qxF 'require("ava-shijima")' "$HYPR_DIR/hyprland.lua" 2>/dev/null; then
        note "hyprland.lua already requires ava-shijima"
      else
        [ -f "$HYPR_DIR/hyprland.lua.ava-bak" ] || cp -p "$HYPR_DIR/hyprland.lua" "$HYPR_DIR/hyprland.lua.ava-bak" || die "cannot back up hyprland.lua"
        printf '\n-- AvA Shimejis / Shijima-Qt window rules\nrequire("ava-shijima")\n' \
          >> "$HYPR_DIR/hyprland.lua"
        note "added require(\"ava-shijima\") to hyprland.lua (backup: hyprland.lua.ava-bak)"
      fi
      RULES_FILE="$RULES_LUA"
      ;;
    *)
      printf '%s\n' "$(rules_text "$flavour")" > "$RULES_CONF" || die "cannot write $RULES_CONF"
      note "wrote $RULES_CONF ($flavour rules)"
      RULES_FILE="$RULES_CONF"
      source_rules_conf
      ;;
  esac
  return 0
}

source_rules_conf() {
  [ -f "$HYPR_DIR/hyprland.conf" ] || return 0
  if grep -qxF "source = $RULES_CONF" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
    note "hyprland.conf already sources $RULES_CONF"
    return 0
  fi
  [ -f "$HYPR_DIR/hyprland.conf.ava-bak" ] || cp -p "$HYPR_DIR/hyprland.conf" "$HYPR_DIR/hyprland.conf.ava-bak" || die "cannot back up hyprland.conf"
  { printf '\n# AvA Shimejis / Shijima-Qt window rules\n'
    printf 'source = %s\n' "$RULES_CONF"; } >> "$HYPR_DIR/hyprland.conf"
  note "added 'source = $RULES_CONF' to hyprland.conf (backup: hyprland.conf.ava-bak)"
}

add_autostart() {
  local launcher; launcher="$(launcher_cmd)"
  if [ -z "$launcher" ]; then
    note "could not find shijima-qt (or its Flatpak) - skipping autostart"
    note "install it, then re-run: $0 --autostart"
    return 0
  fi
  if [ -z "${RULES_FILE:-}" ]; then
    # no Hyprland: GNOME/KDE/XFCE *do* read ~/.config/autostart, so use it
    if ! hypr_present; then
      write_session_helper "$launcher"
      mkdir -p "$(dirname "$XDG_AUTOSTART")" || die "cannot create $(dirname "$XDG_AUTOSTART")"
      local desktop_exec; desktop_exec="$(desktop_quote "$SESSION_HELPER")" || die "cannot quote the session helper path"
      cat > "$XDG_AUTOSTART" <<EOF || die "cannot write $XDG_AUTOSTART"
[Desktop Entry]
Type=Application
Name=AVA Shijima-Qt
Comment=Start Shijima-Qt and its four mascots when the session starts
Exec=$desktop_exec
Terminal=false
X-GNOME-Autostart-enabled=true
NotShowIn=Hyprland;
EOF
      note "autostart: $XDG_AUTOSTART (read by GNOME, KDE, XFCE...)"
    else
      note "no Hyprland rules file to autostart from - skipping autostart"
    fi
    return 0
  fi

  write_session_helper "$launcher"
  local quoted; quoted="$(shell_quote "$SESSION_HELPER")"

  if grep -qF "$SESSION_HELPER" "$RULES_FILE" 2>/dev/null; then
    note "autostart already present in $RULES_FILE"
    return 0
  fi
  case "$RULES_FILE" in
    *.lua)
      { printf '\n-- Start Shijima-Qt with the session and put the four on screen.\n'
        printf 'hl.on("hyprland.start", function()\n'
        printf '  hl.exec_cmd(%s)\n' "$(lua_quote "$quoted")"
        printf 'end)\n'; } >> "$RULES_FILE"
      note "autostart: hl.on(\"hyprland.start\", ...) -> $RULES_FILE"
      ;;
    *)
      { printf '\n# Start Shijima-Qt with the session and put the four on screen.\n'
        printf '# (Hyprland never reads ~/.config/autostart, so Shijima-Qt cannot\n'
        printf '#  do this by itself - this line is what brings it back.)\n'
        printf 'exec-once = %s\n' "$quoted"; } >> "$RULES_FILE"
      note "autostart: exec-once = $quoted"
      ;;
  esac
}
# ---------------------------------------------------------------- check
check() {
  # unpredictable names: a fixed /tmp path could be a symlink planted by someone else
  CHECK_JSON="$(mktemp)" || die "cannot create a temp file"
  CLIENTS_JSON="$(mktemp)" || die "cannot create a temp file"
  trap 'rm -f "$CHECK_JSON" "$CLIENTS_JSON"' EXIT
  local dir; dir="$(first_existing_mascot_dir || true)"
  note "Shijima-Qt mascots folder : ${dir:-(not found yet - has Shijima-Qt ever run?)}"
  note "build output              : $OUT $([ -d "$OUT" ] && echo "(present)" || echo "(not built)")"
  note "binary                    : $(command -v shijima-qt || echo 'not on PATH')"
  local run
  run="$(pgrep -x shijima-qt 2>/dev/null | head -1)"
  [ -z "$run" ] && run="$(pgrep -af 'com.pixelomer.ShijimaQt' 2>/dev/null | head -1)"
  note "running                   : ${run:-no}"
  if [ -n "${dir:-}" ] && [ -d "$dir" ]; then
    local n; n="$(find "$dir" -mindepth 1 -maxdepth 1 -type d -name '*.mascot' -printf . | wc -c | tr -d ' ')"
    note "installed mascots         : $n"
    find "$dir" -mindepth 1 -maxdepth 1 -type d -name '*.mascot' -printf '      %p\n'
  fi
  if command -v curl >/dev/null 2>&1; then
    if curl --noproxy '*' -fsS -m 2 "http://127.0.0.1:32456/shijima/api/v1/loadedMascots" >"$CHECK_JSON" 2>/dev/null && [ -s "$CHECK_JSON" ]; then
      note "Shijima-Qt is up; mascots it knows about:"
      python3 - "$CHECK_JSON" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as exc:
    print("      (could not parse the API response: %s)" % exc)
    raise SystemExit
for m in data.get("loaded_mascots", []):
    print("      id=%s name=%r" % (m.get("id"), m.get("name")))
PY
    else
      note "API                       : unreachable (app stopped, or API unavailable)"
    fi
    if curl --noproxy '*' -fsS -m 2 "$MASCOTS_URL" >"$CHECK_JSON" 2>/dev/null && [ -s "$CHECK_JSON" ]; then
      python3 - "$CHECK_JSON" <<'PY_LIVE'
from collections import Counter
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    mascots = data["mascots"]
    if not isinstance(mascots, list) or any(
            not isinstance(m, dict) or not isinstance(m.get("name"), str) for m in mascots):
        raise ValueError("expected a list of named mascots")
    counts = Counter(m["name"] for m in mascots)
except (OSError, ValueError, KeyError, TypeError) as exc:
    print("  live mascot count         : unknown (invalid API response: %s)" % exc)
else:
    print("  live mascot count         : %d (not the number of installed packs)" % len(mascots))
    for name, count in sorted(counts.items()):
        print("      %s: %d%s" % (name, count, " (extra copies)" if count > 1 else ""))
PY_LIVE
    else
      note "live mascot count         : unavailable (GET /mascots did not answer)"
    fi
  else
    note "API diagnostics           : install curl to report live mascot counts"
  fi
  note "hyprland config style     : $(hypr_flavour)"
  note "session helper            : $([ -f "$SESSION_HELPER_PATH" ] \
                                    && echo "$SESSION_HELPER_PATH" || echo 'not written')"
  note "XDG autostart entry       : $([ -f "$XDG_AUTOSTART" ] \
                                    && echo "$XDG_AUTOSTART" || echo 'not written')"
  note "hyprland rules            : $(if [ -f "$RULES_CONF" ]; then echo "$RULES_CONF";
                                    elif [ -f "$RULES_LUA" ]; then echo "$RULES_LUA"; else echo 'not written'; fi)"
  if hypr_present && command -v hyprctl >/dev/null 2>&1; then
    note "windows Hyprland can see:"
    hyprctl clients -j 2>/dev/null > "$CLIENTS_JSON"
    python3 - "$CLIENTS_JSON" <<'PY'
import json, sys
try:
    windows = json.load(open(sys.argv[1]))
except Exception:
    windows = []
found = 0
for w in windows:
    cls = str(w.get("class") or "") + str(w.get("initialClass") or "")
    title = str(w.get("title") or "")
    if "shijima" not in cls.lower() and "shijima" not in title.lower():
        continue
    found += 1
    print("      {addr} class={cls!r} at={at} size={size} floating={floating} border={border}".format(
        addr=w.get("address"), cls=w.get("class"), at=w.get("at"), size=w.get("size"),
        floating=w.get("floating"), border=w.get("borderSize")))
if not found:
    print("      (no shijima windows right now - start it first)")
PY
    rm -f "$CLIENTS_JSON"
  fi
  echo
  note "Several moving stickmen inside ONE shared box? Check Shijima's Windowed mode."
  note "  Right-click a stickman -> Show manager -> Settings:"
  note "    uncheck Enable multiplication, then uncheck Windowed mode."
  note "  Right-click -> Dismiss all clears the current crowd without deleting imports."
  note "  In the manager, double-click Blue, Orange, Yellow and Green once each."
  note "Windowed mode is a live app setting, not a Hyprland border rule."
  note "Shijima's API does not report or change this mode; verify the checkbox in the app."
  note "This check only reads state; it never spawns additional mascots."
}

uninstall() {
  local dir; dir="$(first_existing_mascot_dir || true)"
  if [ -n "${dir:-}" ]; then
    local char
    for char in Blue Orange Yellow Green; do
      [ -e "$dir/$char.mascot" ] && rm -rf "$dir/$char.mascot" && note "removed $dir/$char.mascot"
      for old in "$dir/$char.mascot.old-"*; do
        [ -e "$old" ] || continue
        if [ -e "$dir/$char.mascot" ]; then
          note "left $old in place (it was an older copy of the same import)"
        else
          mv "$old" "$dir/$char.mascot" && note "restored $dir/$char.mascot"
        fi
      done
    done
  fi
  local settings; settings="$(settings_file)"
  if [ -f "$settings.ava-bak" ]; then
    cp -p "$settings.ava-bak" "$settings" || die "cannot restore $settings"
    rm -f "$settings.ava-bak"
    note "restored $settings"
  fi
  for helper in "$SESSION_HELPER_PATH" "$DATA_DIR/shijima-session.py" "$HYPR_DIR/ava-shijima-session.sh"; do
    [ -f "$helper" ] && rm -f "$helper" && note "removed $helper"
  done
  rmdir "$DATA_DIR" 2>/dev/null || true
  [ -f "$XDG_AUTOSTART" ] && rm -f "$XDG_AUTOSTART" && note "removed $XDG_AUTOSTART"
  if [ -f "$RULES_LUA" ]; then
    if [ -f "$HYPR_DIR/hyprland.lua" ] && grep -qxF 'require("ava-shijima")' "$HYPR_DIR/hyprland.lua"; then
      python3 - "$HYPR_DIR/hyprland.lua" <<'PY'
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
out = []
for l in lines:
    if 'require("ava-shijima")' in l:
        if out and out[-1].lstrip().startswith("-- AvA Shimejis"):
            out.pop()
        continue
    out.append(l)
open(path, "w", encoding="utf-8", errors="surrogateescape").writelines(out)
print("  dropped require(\"ava-shijima\") from", path)
PY
    fi
    rm -f "$RULES_LUA" && note "removed $RULES_LUA"
  fi
  for conf in "$RULES_CONF" "$HYPR_DIR/ava-shimeji.conf"; do
    [ -f "$conf" ] || continue
    python3 - "$conf" <<'PY'
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
keep = [l for l in lines if not (l.startswith("exec-once") and "shijima" in l)]
open(path, "w", encoding="utf-8", errors="surrogateescape").writelines(keep)
PY
    note "dropped the autostart line from $conf"
  done
  if [ -f "$RULES_CONF" ]; then
    local main="$HYPR_DIR/hyprland.conf"
    if [ -f "$main" ] && grep -qxF "source = $RULES_CONF" "$main"; then
      python3 - "$main" "$RULES_CONF" <<'PY'
import sys
path, needle = sys.argv[1], f"source = {sys.argv[2]}"
out = []
for line in open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True):
    if needle in line:
        # the comment line we wrote above it goes too
        if out and out[-1].lstrip().startswith("# AvA Shimejis"):
            out.pop()
        continue
    out.append(line)
# drop the blank line left at the very end of the file
while out and not out[-1].strip():
    out.pop()
if out and not out[-1].endswith("\n"):
    out[-1] += "\n"
open(path, "w", encoding="utf-8", errors="surrogateescape").writelines(out)
print("  dropped the source line from", path)
PY
    fi
    rm -f "$RULES_CONF" && note "removed $RULES_CONF"
  fi
  command -v hyprctl >/dev/null 2>&1 && hyprctl reload >/dev/null 2>&1 && note "reloaded Hyprland"
  note "Shijima-Qt may still list the mascots until it is restarted."
}

# ---------------------------------------------------------------- main
case "$MODE" in
  check)     echo "Shijima-Qt pack status:"; check ;;
  uninstall) echo "Undoing the Shijima-Qt setup:"; uninstall ;;
  *)
    echo "Building Shijima-Qt mascots:"
    build
    if [ "$MODE" = install ]; then
      prepare_install
      install_mascots
      python3 "$REPO/linux/configure-mascots.py" shijima "$(settings_file)" || die "cannot disable multiplication"
    fi
    # Window rules are needed even if the user does not want autostart.
    if [ "$MODE" = install ] || $DO_AUTOSTART; then
      write_rules || exit 1
      if $DO_AUTOSTART; then add_autostart || exit 1; fi
      if [ -n "$RULES_FILE" ] && command -v hyprctl >/dev/null 2>&1; then
        hypr_reload || exit 1
      fi
    fi
    if $DO_RESTART; then
      launcher="$(launcher_cmd)"
      [ -n "$launcher" ] || die "cannot find shijima-qt or its Flatpak"
      write_session_helper "$launcher"
      "$SESSION_HELPER" || die "could not restart the repaired crew"
    fi
    ;;
esac

if [ "$MODE" != check ] && [ "$MODE" != uninstall ]; then
  echo
  echo "Next:"
  if [ "$MODE" = build ]; then
    echo "  * import $OUT/<Character>.mascot.zip in Shijima-Qt (File -> Import), or"
    echo "    re-run with --install to copy the .mascot folders in directly."
  elif ! $DO_RESTART; then
    echo "  * launch Shijima-Qt again to load the repaired pack, or use --install --autostart --restart."
  fi
  echo "  * if all mascots share one box, turn off Settings -> Windowed mode in Shijima."
  echo "  * multiplication is disabled in the installed pack and host settings."
  echo "  * do not also run Shimeji-ee or ava-runner; each host adds its own crew."
  echo "  * status any time: $0 --check"
fi
