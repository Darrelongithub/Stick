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
#   ./linux/shijima.sh --check         # report what is where
#   ./linux/shijima.sh --uninstall     # remove what --install/--autostart added
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${SHIJIMA_BUILD_DIR:-$REPO/build/shijima}"
HYPR_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
RULES_CONF="$HYPR_DIR/ava-shijima-qt.conf"
SPAWN_URL="http://127.0.0.1:32456/shijima/api/v1/mascots"

MODE="build"
DO_AUTOSTART=false
RULES_FILE=""
SESSION_HELPER=""

die() { echo "ERROR: $*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --install)   MODE="install" ;;
    --autostart) DO_AUTOSTART=true ;;
    --check)     MODE="check" ;;
    --uninstall) MODE="uninstall" ;;
    --out)       shift; [ $# -gt 0 ] || die "--out needs a path"; OUT="$1" ;;
    --out=*)     OUT="${1#*=}" ;;
    -h|--help)   sed -n '2,/^set -u$/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           die "unknown option: $1" ;;
  esac
  shift
done

# ---------------------------------------------------------------- locations
is_flatpak_install() {
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
  rm -rf "$OUT"
  mkdir -p "$OUT" || die "cannot create $OUT"
  for char in $chars; do
    src="$REPO/AVA Shimejis/$char"
    [ -d "$src" ] || die "missing image set $src"
    [ -f "$src/conf/actions.xml" ] || die "$src/conf/actions.xml is missing"
    dest="$OUT/$char.mascot"
    mkdir -p "$dest/img" || die "cannot create $dest"
    cp "$src/conf/actions.xml" "$dest/actions.xml" || die "cannot copy actions.xml"
    cp "$src/conf/behaviors.xml" "$dest/behaviors.xml" || die "cannot copy behaviors.xml"
    cp "$src"/*.png "$dest/img/" 2>/dev/null || die "no frames found in $src"
    note "$char.mascot  ($(ls "$dest/img" | wc -l | tr -d ' ') frames)"
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
    dir="${XDG_DATA_HOME:-$HOME/.local/share}/Shijima-Qt/mascots"
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
  # lua | v1 | v2 | v3 | unknown
  if [ -f "$HYPR_DIR/hyprland.lua" ] && [ ! -f "$HYPR_DIR/hyprland.conf" ]; then
    printf 'lua'; return
  fi
  command -v hyprctl >/dev/null 2>&1 || { printf 'unknown'; return; }
  local tag major minor
  tag="$(hyprctl version -j 2>/dev/null | sed -n 's/.*"tag"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  major="$(printf '%s' "$tag" | sed -n 's/^v\{0,1\}\([0-9]\+\)\..*/\1/p')"
  minor="$(printf '%s' "$tag" | sed -n 's/^v\{0,1\}[0-9]\+\.\([0-9]\+\).*/\1/p')"
  if [ -n "${major:-}" ] && [ -n "${minor:-}" ]; then
    if [ "$major" -gt 0 ] || [ "$minor" -ge 53 ]; then printf 'v3'
    elif [ "$minor" -ge 44 ]; then printf 'v2'
    else printf 'v1'; fi
  else
    printf 'unknown'
  fi
}

rules_text() {
  case "$1" in
    va) cat <<EOF
# Managed by linux/shijima.sh.  Shijima-Qt draws each mascot in its own X11
# window; without these rules Hyprland tiles it and paints a border, shadow and
# blur around it - the "box".
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
    v3) cat <<EOF
# Managed by linux/shijima.sh.  Shijima-Qt draws each mascot in its own X11
# window; without these rules Hyprland tiles it and paints a border, shadow and
# blur around it - the "box".
windowrule = float,        match :class ^($CLASS_REGEX)\$
windowrule = nofocus,      match :class ^($CLASS_REGEX)\$
windowrule = noborder,     match :class ^($CLASS_REGEX)\$
windowrule = noshadow,     match :class ^($CLASS_REGEX)\$
windowrule = noblur,       match :class ^($CLASS_REGEX)\$
windowrule = noanim,       match :class ^($CLASS_REGEX)\$
windowrule = rounding 0,   match :class ^($CLASS_REGEX)\$
windowrule = bordersize 0, match :class ^($CLASS_REGEX)\$
EOF
      ;;
  esac
}

lua_rules_text() {
  cat <<EOF
-- Managed by linux/shijima.sh (Hyprland 0.55+ / hyprland.lua).
-- Shijima-Qt draws each mascot in its own window; without these rules
-- Hyprland tiles it and paints a border and shadow around it - the "box".
hl.window_rule({
  name  = "ava-shijima-qt",
  match = { class = "$CLASS_REGEX" },
  float = true, no_focus = true, no_border = true,
  no_shadow = true, no_blur = true, no_anim = true,
  rounding = 0, border_size = 0,
})
EOF
}

launcher_cmd() {
  if command -v shijima-qt >/dev/null 2>&1; then printf 'shijima-qt'; return; fi
  if command -v flatpak >/dev/null 2>&1 \
     && flatpak list --app 2>/dev/null | grep -qi 'com.pixelomer.ShijimaQt'; then
    printf 'flatpak run com.pixelomer.ShijimaQt'; return
  fi
  printf ''
}

# One tiny script instead of an un-quotable one-liner: it starts Shijima-Qt if
# it is not already up, waits for its HTTP API, then asks for the four mascots
# (Shijima-Qt always opens with an empty screen).
write_session_helper() {
  local launcher="$1"
  SESSION_HELPER="$HYPR_DIR/ava-shijima-session.sh"
  cat > "$SESSION_HELPER" <<EOF || die "cannot write $SESSION_HELPER"
#!/usr/bin/env sh
# Written by linux/shijima.sh - start Shijima-Qt with the Hyprland session and
# put the four characters on screen.  Hyprland never reads ~/.config/autostart,
# so this is what makes Shijima-Qt come back after a reboot.
set -u
if ! pgrep -f 'shijima-qt|Shijima-Qt' >/dev/null 2>&1; then
  nohup $launcher >/dev/null 2>&1 &
fi
sleep 8
for m in Blue Orange Yellow Green; do
  python3 - "\$m" <<'PY'
import json, sys, urllib.request
name = sys.argv[1]
req = urllib.request.Request(
    "http://127.0.0.1:32456/shijima/api/v1/mascots",
    data=json.dumps({"name": name}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=5)
except Exception as exc:                 # app not up yet / name not loaded
    sys.stderr.write(f"ava-shijima: could not spawn {name}: {exc}\n")
PY
done
EOF
  chmod +x "$SESSION_HELPER" || die "cannot make $SESSION_HELPER executable"
  note "wrote $SESSION_HELPER"
}

# shell-quote a path for hyprlang / Lua
quote_path() {
  # a plain path is fine for hyprlang; only whitespace needs quoting, and
  # then it has to survive /bin/sh too, so single-quote it
  case "$1" in
    *" "*) printf "'%s'" "$1" ;;
    *)     printf %s "$1" ;;
  esac
}

lua_escape() {
  printf '%s' "$1" | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g'
}

write_rules() {
  hypr_present || { note "no Hyprland config here - skipping window rules and autostart"; return 1; }
  local flavour; flavour="$(hypr_flavour)"
  case "$flavour" in
    lua)
      printf '%s\n' "$(lua_rules_text)" > "$RULES_LUA" || die "cannot write $RULES_LUA"
      note "wrote $RULES_LUA"
      if grep -qF 'require("ava-shijima")' "$HYPR_DIR/hyprland.lua" 2>/dev/null; then
        note "hyprland.lua already requires ava-shijima"
      else
        cp -p "$HYPR_DIR/hyprland.lua" "$HYPR_DIR/hyprland.lua.ava-bak" 2>/dev/null || true
        printf '\n-- AvA Shimejis / Shijima-Qt window rules\nrequire("ava-shijima")\n' \
          >> "$HYPR_DIR/hyprland.lua"
        note "added require(\"ava-shijima\") to hyprland.lua (backup: hyprland.lua.ava-bak)"
      fi
      RULES_FILE="$RULES_LUA"
      ;;
    unknown)
      note "could not tell which Hyprland config style is in use - writing the modern"
      note "(0.53+) rules; if they are not picked up, run this again after hyprctl exists."
      printf '%s\n' "$(rules_text v3)" > "$RULES_CONF"
      RULES_FILE="$RULES_CONF"
      source_rules_conf
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
  if grep -qF "source = $RULES_CONF" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
    note "hyprland.conf already sources $RULES_CONF"
    return 0
  fi
  cp -p "$HYPR_DIR/hyprland.conf" "$HYPR_DIR/hyprland.conf.ava-bak" 2>/dev/null || true
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
  [ -n "${RULES_FILE:-}" ] || { note "no Hyprland rules file to autostart from - skipping"; return 0; }

  write_session_helper "$launcher"
  local quoted; quoted="$(quote_path "$SESSION_HELPER")"

  if grep -qF "$SESSION_HELPER" "$RULES_FILE" 2>/dev/null; then
    note "autostart already present in $RULES_FILE"
    return 0
  fi
  case "$RULES_FILE" in
    *.lua)
      { printf '\n-- Start Shijima-Qt with the session and put the four on screen.\n'
        printf 'hl.on("hyprland.start", function()\n'
        printf '  hl.exec_cmd("%s")\n' "$(lua_escape "$SESSION_HELPER")"
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
  local dir; dir="$(first_existing_mascot_dir || true)"
  note "Shijima-Qt mascots folder : ${dir:-(not found yet - has Shijima-Qt ever run?)}"
  note "build output              : $OUT $([ -d "$OUT" ] && echo "(present)" || echo "(not built)")"
  note "binary                    : $(command -v shijima-qt || echo 'not on PATH')"
  local run
  run="$(pgrep -x shijima-qt 2>/dev/null | head -1)"
  [ -z "$run" ] && run="$(pgrep -af 'com.pixelomer.ShijimaQt' 2>/dev/null | head -1)"
  note "running                   : ${run:-no}"
  if [ -n "${dir:-}" ] && [ -d "$dir" ]; then
    local n; n="$(ls -d "$dir"/*.mascot 2>/dev/null | wc -l | tr -d ' ')"
    note "installed mascots         : $n"
    ls -d "$dir"/*.mascot 2>/dev/null | sed 's/^/      /' || true
  fi
  if command -v curl >/dev/null 2>&1; then
    if curl -s -m 2 "http://127.0.0.1:32456/shijima/api/v1/loadedMascots" >/tmp/.ava-check.json 2>/dev/null && [ -s /tmp/.ava-check.json ]; then
      note "Shijima-Qt is up; mascots it knows about:"
      python3 - /tmp/.ava-check.json <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as exc:
    print("      (could not parse the API response: %s)" % exc)
    raise SystemExit
for m in data.get("loaded_mascots", []):
    print("      id=%s name=%r" % (m.get("id"), m.get("name")))
PY
      rm -f /tmp/.ava-check.json
    else
      note "API                       : no response (Shijima-Qt is not running)"
      rm -f /tmp/.ava-check.json
    fi
  fi
  note "hyprland config style     : $(hypr_flavour)"
  note "session helper            : $([ -f "$HYPR_DIR/ava-shijima-session.sh" ] \
                                    && echo "$HYPR_DIR/ava-shijima-session.sh" || echo 'not written')"
  note "hyprland rules            : $([ -f "$RULES_CONF" ] && echo "$RULES_CONF" \
                                    || { [ -f "$RULES_LUA" ] && echo "$RULES_LUA" || echo 'not written'; })"
  if hypr_present && command -v hyprctl >/dev/null 2>&1; then
    note "windows Hyprland can see:"
    hyprctl clients -j 2>/dev/null > /tmp/.ava-clients.json
    python3 - /tmp/.ava-clients.json <<'PY'
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
    rm -f /tmp/.ava-clients.json
  fi
  echo
  note "Spawn one by hand (Shijima-Qt must be running):"
  local example='{"name":"Blue"}'  # shown to the user, not executed here
  note "  curl -X POST $SPAWN_URL -H 'Content-Type: application/json' -d '$example'"
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
  rm -f "$HYPR_DIR/ava-shijima-session.sh" 2>/dev/null && note "removed the session helper"
  if [ -f "$RULES_LUA" ]; then
    if [ -f "$HYPR_DIR/hyprland.lua" ] && grep -qF 'require("ava-shijima")' "$HYPR_DIR/hyprland.lua"; then
      python3 - "$HYPR_DIR/hyprland.lua" <<'PY'
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
out, skip = [], 0
for l in lines:
    if skip:                      # also drop the comment line above it
        skip = 0
        continue
    if 'require("ava-shijima")' in l:
        if out and out[-1].lstrip().startswith("-- AvA Shimejis"):
            out.pop()
        skip = 1
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
    if [ -f "$main" ] && grep -qF "source = $RULES_CONF" "$main"; then
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
  *)         echo "Building Shijima-Qt mascots:"; build
             [ "$MODE" = "install" ] && install_mascots
             if $DO_AUTOSTART; then write_rules && add_autostart; fi ;;
esac

if [ "$MODE" != "check" ] && [ "$MODE" != "uninstall" ]; then
  echo
  echo "Next:"
  if [ "$MODE" = "build" ]; then
    echo "  * import $OUT/<Character>.mascot.zip in Shijima-Qt (File -> Import), or"
    echo "    re-run with --install to copy the .mascot folders in directly."
  fi
  echo "  * they are still one of each: Shijima-Qt loads a mascot per spawn,"
  echo "    and this pack has breeding switched off, so it stays at four."
  echo "  * status any time: $0 --check"
fi
