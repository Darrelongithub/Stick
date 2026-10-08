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
#   ./linux/hyprland.sh --no-start      # don't launch them at the end
#   ./linux/hyprland.sh --uninstall     # remove everything it added
#   ./linux/hyprland.sh --syntax v2     # force: auto|v1|v2|v3|lua|x11
#   ./linux/hyprland.sh /path/to/shimeji-ee
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
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
FORCED_SYNTAX=""
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
    --syntax)    shift; [ $# -gt 0 ] || die "--syntax needs a value"; SYNTAX="$1"; FORCED_SYNTAX="$1" ;;
    --syntax=*)  SYNTAX="${1#*=}"; FORCED_SYNTAX="${1#*=}" ;;
    -h|--help)   sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
JAR="$(ls "$TARGET"/Shimeji-ee.jar "$TARGET"/Shimeji.jar "$TARGET"/*himeji*.jar 2>/dev/null | head -n 1)"
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
  if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    note "session: Hyprland on Wayland (shimejis run through XWayland)"
  else
    note "session: Hyprland on X11"
  fi
else
  note "session: not Hyprland (${XDG_CURRENT_DESKTOP:-unknown}) - writing X11-friendly setup only"
fi

hypr_version() {
  command -v hyprctl >/dev/null 2>&1 || return 1
  local out tag
  out="$(hyprctl version -j 2>/dev/null)" || true
  tag="$(printf '%s' "$out" | sed -n 's/.*"tag"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  if [ -z "$tag" ]; then
    out="$(hyprctl version 2>/dev/null)" || true
    tag="$(printf '%s' "$out" | sed -n 's/.*tags\?\/v\{0,1\}\([0-9][0-9.]*\).*/v\1/p' | head -n 1)"
  fi
  printf '%s' "$tag"
}

pick_syntax() {
  [ "$SYNTAX" != "auto" ] && { printf '%s' "$SYNTAX"; return; }
  if [ -f "$MAIN_LUA" ]; then printf 'lua'; return; fi
  if [ ! -f "$MAIN_CONF" ]; then printf 'snippet'; return; fi
  local tag major minor
  tag="$(hypr_version)"
  major="$(printf '%s' "$tag" | sed -n 's/^v\{0,1\}\([0-9]\+\)\..*/\1/p')"
  minor="$(printf '%s' "$tag" | sed -n 's/^v\{0,1\}[0-9]\+\.\([0-9]\+\).*/\1/p')"
  if [ -n "${major:-}" ] && [ -n "${minor:-}" ]; then
    if [ "$major" -gt 0 ] || [ "$minor" -ge 55 ]; then printf 'v3'
    elif [ "$minor" -ge 30 ]; then printf 'v2'
    else printf 'v1'; fi
    return
  fi
  # version unknown: 0.53+ accepts the unified `windowrule` form, older builds
  # accept windowrulev2. Emit the v2 form (supported for years) - see --syntax.
  printf 'v2'
}

# ---------------------------------------------------------------- rule text
rules_text() {
  local syn="$1"
  case "$syn" in
    v1)
      cat <<EOF
# Legacy windowrule syntax (Hyprland up to ~0.29)
windowrule = float,    class:^($CLASS_REGEX)\$
windowrule = nofocus,  class:^($CLASS_REGEX)\$
windowrule = noborder, class:^($CLASS_REGEX)\$
windowrule = noshadow, class:^($CLASS_REGEX)\$
windowrule = noblur,   class:^($CLASS_REGEX)\$
windowrule = noanim,   class:^($CLASS_REGEX)\$
EOF
      ;;
    v2)
      cat <<EOF
# windowrulev2 syntax (Hyprland ~0.30 - 0.52)
windowrulev2 = float,     class:^($CLASS_REGEX)\$
windowrulev2 = nofocus,   class:^($CLASS_REGEX)\$
windowrulev2 = noborder,  class:^($CLASS_REGEX)\$
windowrulev2 = noshadow,  class:^($CLASS_REGEX)\$
windowrulev2 = noblur,    class:^($CLASS_REGEX)\$
windowrulev2 = noanim,    class:^($CLASS_REGEX)\$
windowrulev2 = rounding 0, class:^($CLASS_REGEX)\$
windowrulev2 = bordersize 0, class:^($CLASS_REGEX)\$
EOF
      ;;
    v3)
      cat <<EOF
# Unified windowrule syntax (Hyprland 0.53+, hyprlang)
windowrule = float, match :class ^($CLASS_REGEX)\$
windowrule = nofocus, match :class ^($CLASS_REGEX)\$
windowrule = noborder, match :class ^($CLASS_REGEX)\$
windowrule = noshadow, match :class ^($CLASS_REGEX)\$
windowrule = noblur, match :class ^($CLASS_REGEX)\$
windowrule = noanim, match :class ^($CLASS_REGEX)\$
windowrule = rounding 0, match :class ^($CLASS_REGEX)\$
windowrule = bordersize 0, match :class ^($CLASS_REGEX)\$
EOF
      ;;
    x11)
      cat <<EOF
# Running under a non-Hyprland session: the shimeji windows are plain
# override-redirect X11 windows with no decorations, so there is nothing to
# configure here.  (GNOME/X11 will not draw frames around them; GNOME/Wayland
# needs the window to be marked as a dock - see the README.)
EOF
      ;;
  esac
}

lua_text() {
  cat <<EOF
-- Window rules for the AvA Shimejis (Hyprland 0.55+, Lua config).
-- Shimeji-ee puts every character in its own X11 window; without these rules
-- Hyprland tiles it and paints a border/shadow/blur around it ("the box").
hl.window_rule({
  name  = "ava-shimeji",
  match = { class = "$CLASS_REGEX" },
  float = true, no_focus = true, no_border = true,
  no_shadow = true, no_blur = true, no_anim = true,
  rounding = 0, border_size = 0,
})
EOF
}

# ---------------------------------------------------------------- exec line
exec_cmd() {
  if [ "$MODE" = "uninstall" ]; then printf '%s' ""; return; fi
  printf 'java -jar %s' "$(printf '%q' "$JAR")"
}

# ---------------------------------------------------------------- install bits
ensure_conf_source() {
  [ -f "$MAIN_CONF" ] || return 0
  if grep -qF "source = $RULES_CONF" "$MAIN_CONF" 2>/dev/null; then
    note "hyprland.conf already sources $RULES_CONF"
  else
    if [ "$MODE" = "dry" ]; then
      note "would add: source = $RULES_CONF   -> $MAIN_CONF"
    else
      cp -p "$MAIN_CONF" "$MAIN_CONF.ava-bak" 2>/dev/null || true
      { printf '\n%s\n' "$MARKER_BEGIN";
        printf 'source = %s\n' "$RULES_CONF";
        printf '%s\n' "$MARKER_END"; } >> "$MAIN_CONF"
      note "added 'source = $RULES_CONF' to hyprland.conf (backup: hyprland.conf.ava-bak)"
    fi
  fi
}

ensure_exec_once() {
  local cmd="$1" name="ava-shimeji-exec"
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
  if grep -qF 'require("ava-shimeji")' "$MAIN_LUA"; then
    note "hyprland.lua already requires ava-shimeji"
    return 0
  fi
  if [ "$MODE" = "dry" ]; then
    note "would add: require(\"ava-shimeji\") -> $MAIN_LUA"
    return 0
  fi
  cp -p "$MAIN_LUA" "$MAIN_LUA.ava-bak" 2>/dev/null || true
  printf '\n%s\nrequire("ava-shimeji")\n' "$LUA_MARKER" >> "$MAIN_LUA"
  note "added require(\"ava-shimeji\") to hyprland.lua (backup: hyprland.lua.ava-bak)"
}

settings_fix() {
  local file="$TARGET/conf/settings.properties"
  [ -d "$TARGET/conf" ] || return 0
  if [ "$MODE" = "dry" ]; then
    note "would set Breeding=false and ActiveShimeji=Blue/Orange/Yellow/Green in $file"
    return 0
  fi
  [ -f "$file" ] || : > "$file"
  # keep the *first* backup: re-running must not overwrite the pristine copy
  # with an already-patched one (that is what --uninstall restores from).
  [ -f "$file.ava-bak" ] || cp -p "$file" "$file.ava-bak" 2>/dev/null || true
  python3 - "$file" <<'PY'
import re, sys
path = sys.argv[1]
raw = open(path, "rb").read().decode("utf-8", errors="surrogateescape")
eol = "\r\n" if "\r\n" in raw else "\n"   # Shimeji-ee writes CRLF; keep it
head = "#Shimeji-ee Configuration Options" + eol
def put(text, key, value):
    pat = re.compile(r'(?m)^[ \t]*' + re.escape(key) + r'[ \t]*=.*$')
    line = f"{key}={value}"
    if pat.search(text):
        return pat.sub(lambda m: line, text, count=1)
    if text and not text.endswith("\n"):
        text += eol
    return text + line + eol
raw = put(raw, "Breeding", "false")           # no more cloning mid-walk
raw = put(raw, "ActiveShimeji", "Blue/Orange/Yellow/Green")   # exactly four
if not raw.startswith("#"):
    raw = head + raw
raw = re.sub(r"\r?\n", eol, raw)          # don't mix LF into a CRLF file
open(path, "wb").write(raw.encode("utf-8", errors="surrogateescape"))
print("  settings.properties: Breeding=false, ActiveShimeji=Blue/Orange/Yellow/Green")
PY
}

uninstall() {
  say "Removing the Hyprland setup (the shimejis themselves are left installed)."
  for f in "$RULES_CONF" "$RULES_LUA"; do
    [ -f "$f" ] && rm -f "$f" && note "removed $f"
  done
  for pair in "$MAIN_CONF.ava-bak:$MAIN_CONF" "$MAIN_LUA.ava-bak:$MAIN_LUA"; do
    bak="${pair%%:*}"; orig="${pair##*:}"
    if [ -f "$bak" ]; then
      cp -p "$bak" "$orig" && rm -f "$bak" && note "restored $orig from its backup"
    else
      # drop the blocks this script appends, in case there was no backup
      if [ -f "$orig" ]; then
        python3 - "$orig" "$MARKER_BEGIN" "$MARKER_END" "$LUA_MARKER" <<'PY'
import sys
path, mb, me, lm = sys.argv[1:5]
lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
out, skip = [], False
for ln in lines:
    if mb in ln or lm in ln:
        skip = True
        continue
    if skip and (me in ln or 'require("ava-shimeji")' in ln):
        skip = False
        continue
    if skip:
        continue
    out.append(ln)
open(path, "w", encoding="utf-8", errors="surrogateescape").writelines(out)
print(f"  cleaned {path}")
PY
      fi
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
    local count
    count="$(hyprctl clients -j 2>/dev/null | grep -c "$CLASS_REGEX" || true)"
    note "live shimeji windows: ${count:-0}"
    if [ "${count:-0}" != "0" ]; then
      note "window geometry as Hyprland sees it:"
      hyprctl clients -j 2>/dev/null | python3 -c '
import json,sys
try: data=json.load(sys.stdin)
except Exception: data=[]
for w in data:
    if "com-group_finity-mascot" in (w.get("class") or ""):
        g=w.get("at") or [0,0]; s=w.get("size") or [0,0]
        print(f"      id={w.get(\"address\")} at={g} size={s} floating={w.get(\"floating\")} "
              f"border={w.get(\"borderSize\")} title={w.get(\"title\")!r}")
' || true
    fi
  fi
  say ""
  say "Host app check:"
  if pgrep -af 'shijima|Shijima' >/dev/null 2>&1; then
    note "Shijima-Qt looks like it is running - two runners means two sets of"
    note "shimejis. Stop it first:  pkill -f shijima"
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
case "$syn" in
  snippet)
    say ""
    say "No Hyprland config found at $HYPR_DIR (looked for hyprland.conf and"
    say "hyprland.lua), so there is nothing to edit yet.  Paste this into your"
    say "Hyprland config once it exists - it is the whole fix for the boxes:"
    say ""
    rules_text "${FORCED_SYNTAX:-v2}" | sed 's/^/  /'
    say ""
    say "  # ...and to start them with the session (Hyprland ignores"
    say "  # ~/.config/autostart, which is why they never came back on login):"
    say "  exec-once = $(exec_cmd)"
    say ""
    ;;
  x11)
    note "no window rules needed on this session"
    ;;
  lua)
    if [ "$MODE" = "dry" ]; then
      note "would write $RULES_LUA"; lua_text | sed 's/^/      /'
    else
      lua_text > "$RULES_LUA"
      note "wrote $RULES_LUA"
      ensure_lua_require
      ensure_exec_once "$(exec_cmd)"
    fi
    ;;
  *)
    if [ "$MODE" = "dry" ]; then
      note "would write $RULES_CONF"; rules_text "$syn" | sed 's/^/      /'
      note "would run: exec-once = $(exec_cmd)"
    else
      {
        printf '# Managed by linux/hyprland.sh - re-run it after moving Shimeji-ee.\n'
        rules_text "$syn"
      } > "$RULES_CONF"
      note "wrote $RULES_CONF"
      ensure_conf_source
      ensure_exec_once "$(exec_cmd)"
    fi
    ;;
esac

settings_fix

# the XDG autostart entry install.sh writes is dead weight on Hyprland
if [ -f "$HOME/.config/autostart/ava-shimeji.desktop" ]; then
  if [ "$MODE" = "dry" ]; then
    note "would neutralise ~/.config/autostart/ava-shimeji.desktop (Hyprland ignores it)"
  else
    # only a shell running the toggle script - not an editor that has it open
    pkill -f '^(/[^ ]*/)?(ba|da|z)?sh .*ava-toggle[.]sh' >/dev/null 2>&1 || true
    if ! grep -q '^X-GNOME-Autostart-enabled=false' "$HOME/.config/autostart/ava-shimeji.desktop" 2>/dev/null; then
      sed -i 's/^X-GNOME-Autostart-enabled=.*/X-GNOME-Autostart-enabled=false/' \
        "$HOME/.config/autostart/ava-shimeji.desktop" 2>/dev/null || true
      note "left the .desktop for GNOME/KDE users, disabled for XDG autostart"
    fi
  fi
fi

if [ "$MODE" = "dry" ]; then
  say ""
  say "Dry run - nothing was written."
  exit 0
fi

if command -v hyprctl >/dev/null 2>&1; then
  hyprctl reload >/dev/null 2>&1 && note "Hyprland reloaded" || note "hyprctl reload failed (reload manually with: hyprctl reload)"
fi

say ""
if [ "$syn" = "snippet" ]; then
  say "Nothing was written to a Hyprland config (none found).  Settings in the"
  say "Shimeji-ee folder were updated, so once you paste the snippet above you"
  say "are done."
else
  say "Done. Window rules + autostart are in place."
fi
if $DO_START; then
  if [ -x "$TARGET/ava-toggle.sh" ]; then
    say "Starting the shimejis..."
    "$TARGET/ava-toggle.sh" || true
  else
    say "Start them with:  java -jar \"$JAR\" &"
  fi
fi
say "Check the result any time:  $0 --check"
