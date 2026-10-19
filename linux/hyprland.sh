#!/usr/bin/env bash
# Make the AvA Shimejis behave on Hyprland (and on plain X11, harmlessly).
#
# What this fixes, and why each thing is needed:
#
#   1. THE BOX.  Shimeji-ee draws each shimeji into its own borderless X11
#      window (class com-group_finity-mascot-Main).  Hyprland tiles every new
#      window by default and paints its border, shadow and blur around it - so
#      each shimeji appears inside a highlighted box and gets resized.  Window
#      rules fix that (Hyprland's own wiki has a Shimeji recipe for exactly
#      this reason).
#   2. AUTOSTART.  Hyprland does not implement XDG autostart, so the
#      ~/.config/autostart/ava-shimeji.desktop that install.sh writes is never
#      run (and Shijima-Qt, which relies on the same mechanism, never starts
#      either).  This writes a Hyprland `exec-once` instead.
#   3. THE CROWD.  Shimeji-ee's Breeding default lets every character clone
#      itself (up to 50).  It is switched off here, in conf/settings.properties
#      and in each character's behaviours.xml.
#
# Usage:
#   ./linux/hyprland.sh                 # install rules + autostart, then start
#   ./linux/hyprland.sh --check         # report only, change nothing
#   ./linux/hyprland.sh --dry-run       # show what would change
#   ./linux/hyprland.sh --no-start      # apply repairs, leave them stopped
#   ./linux/hyprland.sh --uninstall     # remove everything it added
#   ./linux/hyprland.sh --syntax v2     # force: auto|v1|v2|v3|lua|x11
#   ./linux/hyprland.sh /path/to/shimeji-ee
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/linux/hyprland-common.sh"
CLASS_REGEX="com-group_finity-mascot-Main"
HYPR_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
RULES_CONF="$HYPR_DIR/ava-shimeji.conf"
RULES_LUA="$HYPR_DIR/ava-shimeji.lua"
MAIN_CONF="$HYPR_DIR/hyprland.conf"
MAIN_LUA="$HYPR_DIR/hyprland.lua"
MARKER_BEGIN="# ---- AvA Shimejis (added by linux/hyprland.sh) ----"
MARKER_END="# ---- end AvA Shimejis ----"
LUA_MARKER='-- ---- AvA Shimejis (added by linux/hyprland.sh) ----'

TARGET=""
SYNTAX="auto"
DO_START=true
MODE="install"

die() { echo "ERROR: $*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
note() { printf '  %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --check)     MODE="check" ;;
    --dry-run)   MODE="dry" ;;
    --uninstall) MODE="uninstall" ;;
    --no-start)  DO_START=false ;;
    --start)     DO_START=true ;;
    --syntax)    shift; [ $# -gt 0 ] || die "--syntax needs a value"; SYNTAX="$1" ;;
    --syntax=*)  SYNTAX="${1#*=}" ;;
    -h|--help)   sed -n '2,/^set -u$/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)          die "unknown option: $1" ;;
    *)           [ -z "$TARGET" ] || die "unexpected argument: $1"; TARGET="$1" ;;
  esac
  shift
done

case "$SYNTAX" in auto|v1|v2|v3|lua|x11) ;; *) die "--syntax must be auto, v1, v2, v3, lua or x11";; esac

# ---------------------------------------------------------------- locate shimeji
if [ -z "$TARGET" ]; then
  for d in "$HOME/Shimeji-ee" "$HOME/shimeji-ee" "$HOME/Shimeji" /opt/shimeji-ee /opt/Shimeji-ee; do
    [ -d "$d" ] && TARGET="$d" && break
  done
fi
[ -n "$TARGET" ] && [ -d "$TARGET" ] || die \
  "could not find your Shimeji-ee folder - run: $0 /path/to/shimeji-ee"
TARGET="$(cd "$TARGET" && pwd -P)"
JAR=""
for candidate in "$TARGET/Shimeji-ee.jar" "$TARGET/Shimeji.jar" "$TARGET"/*himeji*.jar; do
  if [ -f "$candidate" ]; then JAR="$candidate"; break; fi
done
[ -n "${JAR:-}" ] || die "no Shimeji jar found in $TARGET"

# ---------------------------------------------------------------- desktop
onsession() {
  [ "${XDG_CURRENT_DESKTOP:-}" ] && case "${XDG_CURRENT_DESKTOP:-}" in
    *[Hh]yprland*) return 0 ;;
  esac
  [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && return 0
  command -v hyprctl >/dev/null 2>&1 && hyprctl version >/dev/null 2>&1 && return 0
  return 1
}
if onsession; then
  note "session: Hyprland (shimejis run through XWayland)"
else
  note "session: not Hyprland (${XDG_CURRENT_DESKTOP:-unknown}) - only configuring any existing Hyprland files"
fi

pick_syntax() {
  if [ "$SYNTAX" = x11 ]; then printf 'x11'; return; fi
  if [ "$SYNTAX" = lua ] && [ ! -f "$MAIN_LUA" ]; then printf 'snippet'; return; fi
  case "$SYNTAX" in
    v1|v2|v3) if [ ! -f "$MAIN_CONF" ]; then printf 'snippet'; return; fi ;;
  esac
  if ! onsession && [ "$SYNTAX" = auto ] && [ ! -f "$MAIN_CONF" ] && [ ! -f "$MAIN_LUA" ]; then printf 'x11'; return; fi
  if [ ! -f "$MAIN_CONF" ] && [ ! -f "$MAIN_LUA" ]; then printf 'snippet'; return; fi
  [ "$SYNTAX" != auto ] && { printf '%s' "$SYNTAX"; return; }
  hypr_syntax "$HYPR_DIR"
}

rules_text() { hypr_rules "$1" "$CLASS_REGEX" ava-shimeji; }
lua_text() { rules_text lua; }

# ---------------------------------------------------------------- exec line
exec_cmd() {
  if [ "$MODE" = "uninstall" ]; then printf '%s' ""; return; fi
  printf '%s --start' "$(shell_quote "$TARGET/ava-toggle.sh")"
}

# ---------------------------------------------------------------- install bits
ensure_conf_source() {
  [ -f "$MAIN_CONF" ] || return 0
  if grep -qxF "source = $RULES_CONF" "$MAIN_CONF" 2>/dev/null; then
    note "hyprland.conf already sources $RULES_CONF"
  else
    if [ "$MODE" = "dry" ]; then
      note "would add: source = $RULES_CONF   -> $MAIN_CONF"
    else
      [ -f "$MAIN_CONF.ava-bak" ] || cp -p "$MAIN_CONF" "$MAIN_CONF.ava-bak" || die "cannot back up $MAIN_CONF"
      { printf '\n%s\n' "$MARKER_BEGIN";
        printf 'source = %s\n' "$RULES_CONF";
        printf '%s\n' "$MARKER_END"; } >> "$MAIN_CONF"
      note "added 'source = $RULES_CONF' to hyprland.conf (backup: hyprland.conf.ava-bak)"
    fi
  fi
}

ensure_exec_once() {
  local cmd="$1"
  [ -f "$RULES_CONF" ] || return 0
  if grep -qF "exec-once" "$RULES_CONF" 2>/dev/null; then
    note "exec-once already present in $RULES_CONF"
  else
    if [ "$MODE" = "dry" ]; then
      note "would add: exec-once = $cmd"
    else
      { printf '# Start the shimejis with the session.  Hyprland does not read\n'
        printf '# ~/.config/autostart, so this is what actually autostarts them.\n'
        printf 'exec-once = %s\n' "$cmd"; } >> "$RULES_CONF"
      note "autostart: exec-once = $cmd"
    fi
  fi
}

ensure_lua_require() {
  [ -f "$MAIN_LUA" ] || return 0
  if grep -qxF 'require("ava-shimeji")' "$MAIN_LUA"; then
    note "hyprland.lua already requires ava-shimeji"
    return 0
  fi
  if [ "$MODE" = "dry" ]; then
    note "would add: require(\"ava-shimeji\") -> $MAIN_LUA"
    return 0
  fi
  [ -f "$MAIN_LUA.ava-bak" ] || cp -p "$MAIN_LUA" "$MAIN_LUA.ava-bak" || die "cannot back up $MAIN_LUA"
  printf '\n%s\nrequire("ava-shimeji")\n' "$LUA_MARKER" >> "$MAIN_LUA"
  note "added require(\"ava-shimeji\") to hyprland.lua (backup: hyprland.lua.ava-bak)"
}

settings_fix() {
  if [ "$MODE" = "dry" ]; then
    note "would stop Shimeji-ee, disable breeding in its installed XML/settings and install the guarded launcher"
    return 0
  fi
  cp "$REPO/linux/ava-toggle.sh" "$TARGET/ava-toggle.sh" || die "cannot install the launcher"
  chmod +x "$TARGET/ava-toggle.sh" || die "cannot make the launcher executable"
  # Java saves settings on exit; stop BEFORE changing them. --no-start leaves
  # it stopped, while the default restarts once after the config is accepted.
  "$TARGET/ava-toggle.sh" --stop || die "could not stop the old Shimeji-ee instance"
  python3 "$REPO/linux/configure-mascots.py" shimeji "$TARGET" || die "could not repair installed settings/XML"
}

uninstall() {
  say "Removing the Hyprland setup (the shimejis themselves are left installed)."
  for f in "$RULES_CONF" "$RULES_LUA"; do
    [ -f "$f" ] && rm -f "$f" && note "removed $f"
  done
  for orig in "$MAIN_CONF" "$MAIN_LUA"; do
    if [ -f "$orig" ]; then
      python3 - "$orig" "$MARKER_BEGIN" "$MARKER_END" "$LUA_MARKER" "$RULES_CONF" <<'PY_CLEAN'
import sys
path, mb, me, lm, rules = sys.argv[1:6]
lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
out, skip = [], False
for ln in lines:
    if mb in ln or lm in ln:
        skip = True
        continue
    if skip and (me in ln or 'require("ava-shimeji")' in ln):
        skip = False
        continue
    if not skip and ln.strip() not in ("source = " + rules, 'require("ava-shimeji")'):
        out.append(ln)
open(path, "w", encoding="utf-8", errors="surrogateescape").writelines(out)
print(f"  cleaned {path} (unrelated edits kept)")
PY_CLEAN
    fi
  done
  if [ -f "$TARGET/conf/settings.properties.ava-bak" ]; then
    cp -p "$TARGET/conf/settings.properties.ava-bak" "$TARGET/conf/settings.properties"
    rm -f "$TARGET/conf/settings.properties.ava-bak"
    note "restored conf/settings.properties"
  fi
  command -v hyprctl >/dev/null 2>&1 && hyprctl reload >/dev/null 2>&1 && note "reloaded Hyprland"
  say "Done. The autostart entry in ~/.config/autostart is separate - see the README."
}

check_report() {
  say "Where things stand:"
  note "shimeji folder : $TARGET"
  note "jar            : $JAR"
  note "hyprland conf  : $([ -f "$MAIN_CONF" ] && echo "$MAIN_CONF" || echo '(none)')"
  note "hyprland lua   : $([ -f "$MAIN_LUA" ] && echo "$MAIN_LUA" || echo '(none)')"
  note "hypr version   : $(hypr_version || echo 'unknown')"
  note "rules syntax   : $(pick_syntax)"
  note "rules file     : $([ -f "$RULES_CONF" ] && echo installed || echo 'not installed')"
  if [ -f "$RULES_CONF" ]; then
    note "autostart      : $(grep -c '^exec-once' "$RULES_CONF" 2>/dev/null || echo 0) exec-once line(s)"
  fi
  if command -v hyprctl >/dev/null 2>&1; then
    hyprctl clients -j 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit("  could not read Hyprland clients")
windows = [w for w in data if "com-group_finity-mascot" in
           ((w.get("class") or "") + (w.get("initialClass") or ""))]
print("  live shimeji windows:", len(windows))
for w in windows:
    print("      id={address} at={at} size={size} floating={floating} title={title!r}".format(
        **{k: w.get(k) for k in ("address", "at", "size", "floating", "title")}))
'
    note "Hyprland config errors (empty means none):"
    hyprctl configerrors 2>/dev/null || true
  fi
  say ""
  say "Host app check:"
  if pgrep -u "$(id -u)" -x 'shijima-qt|Shijima-Qt' >/dev/null 2>&1; then
    note "Shijima-Qt looks like it is running - two runners means two sets of"
    note "shimejis. Quit Shijima-Qt from its menu before starting Shimeji-ee."
  else
    note "no Shijima-Qt process found (good - Shimeji-ee will be the runner)"
  fi
}

# ---------------------------------------------------------------- do it
say "AvA Shimejis x Hyprland"
note "shimeji folder: $TARGET"

if [ "$MODE" = "check" ]; then
  check_report
  exit 0
fi

if [ "$MODE" = "uninstall" ]; then
  uninstall
  exit 0
fi

syn="$(pick_syntax)"
note "rules syntax: $syn"
[ "$syn" != unknown ] || die "cannot detect Hyprland version; run in your desktop session or pass --syntax v2 (0.30-0.52), v3 (0.53+) or lua"
case "$syn" in
  snippet)
    say ""
    say "No Hyprland config found at $HYPR_DIR (looked for hyprland.conf and"
    say "hyprland.lua), so there is nothing to edit yet.  Paste this into your"
    say "Hyprland config once it exists - it is the whole fix for the boxes:"
    say ""
    DO_START=false
    snippet_syntax="$SYNTAX"
    [ "$snippet_syntax" != auto ] || snippet_syntax="$(hypr_syntax "$HYPR_DIR")"
    [ "$snippet_syntax" != unknown ] || die "cannot detect Hyprland version; pass --syntax v2 or v3"
    rules_text "$snippet_syntax" | sed 's/^/  /'
    say ""
    say "  # ...and to start them with the session (Hyprland ignores"
    say "  # ~/.config/autostart, which is why they never came back on login):"
    if [ "$snippet_syntax" = lua ]; then
      say "  hl.on(\"hyprland.start\", function() hl.exec_cmd($(lua_quote "$(exec_cmd)")) end)"
    else
      say "  exec-once = $(exec_cmd)"
    fi
    say ""
    ;;
  x11)
    note "no window rules needed on this session"
    ;;
  lua)
    if [ "$MODE" = "dry" ]; then
      note "would write $RULES_LUA"; lua_text | sed 's/^/      /'
    else
      mkdir -p "$HYPR_DIR" || die "cannot create $HYPR_DIR"
      {
        lua_text
        printf '\nhl.on("hyprland.start", function()\n  hl.exec_cmd(%s)\nend)\n' "$(lua_quote "$(exec_cmd)")"
      } > "$RULES_LUA" || die "cannot write $RULES_LUA"
      note "wrote $RULES_LUA"
      ensure_lua_require
    fi
    ;;
  *)
    if [ "$MODE" = "dry" ]; then
      note "would write $RULES_CONF"; rules_text "$syn" | sed 's/^/      /'
      note "would run: exec-once = $(exec_cmd)"
    else
      mkdir -p "$HYPR_DIR" || die "cannot create $HYPR_DIR"
      {
        printf '# Managed by linux/hyprland.sh - re-run it after moving Shimeji-ee.\n'
        rules_text "$syn"
      } > "$RULES_CONF" || die "cannot write $RULES_CONF"
      note "wrote $RULES_CONF"
      ensure_conf_source
      ensure_exec_once "$(exec_cmd)"
    fi
    ;;
esac

settings_fix

# Desktop sessions using UWSM/systemd may ALSO run XDG autostart. Keep the
# GNOME/KDE entry, but exclude Hyprland using the standard desktop key.
DESKTOP="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/ava-shimeji.desktop"
if [ "$syn" != x11 ] && [ -f "$DESKTOP" ]; then
  if [ "$MODE" = dry ]; then
    note "would exclude Hyprland from $DESKTOP (NotShowIn=Hyprland;)"
  else
    desktop_exec="$(desktop_quote "$TARGET/ava-toggle.sh") --start" || die "cannot quote the launcher path"
    python3 - "$DESKTOP" "$desktop_exec" <<'PY_DESKTOP'
import shutil, sys
from pathlib import Path
path = Path(sys.argv[1])
backup = path.with_name(path.name + ".ava-bak")
if not backup.exists():
    shutil.copy2(path, backup)
text = path.read_text()
lines = text.splitlines()
excluded = {"Hyprland"}
for line in lines:
    if line.startswith("NotShowIn="):
        excluded.update(filter(None, line.split("=", 1)[1].split(";")))
lines = [line for line in lines if not line.startswith(("NotShowIn=", "Exec=", "X-GNOME-Autostart-enabled="))]
lines.extend(["NotShowIn=" + ";".join(sorted(excluded)) + ";",
              "Exec=" + sys.argv[2], "X-GNOME-Autostart-enabled=true"])
path.write_text("\n".join(lines) + "\n")
PY_DESKTOP
  fi
fi

if [ "$MODE" = "dry" ]; then
  say ""
  say "Dry run - nothing was written."
  exit 0
fi

if [ "$syn" != x11 ] && onsession; then
  hypr_reload || exit 1
fi

say ""
if [ "$syn" = "snippet" ]; then
  say "Nothing was written to a Hyprland config (none found).  Settings in the"
  say "Shimeji-ee folder were updated, so once you paste the snippet above you"
  say "are done."
elif [ "$syn" = x11 ]; then
  say "Done. Installed settings repaired; no Hyprland rules were changed."
else
  say "Done. Window rules + guarded autostart are in place."
fi
if $DO_START; then
  if [ -x "$TARGET/ava-toggle.sh" ]; then
    say "Starting the shimejis..."
    "$TARGET/ava-toggle.sh" --start || exit 1
  else
    say "Start them with:  $TARGET/ava-toggle.sh --start"
  fi
fi
say "Check the result any time:  $0 --check"
