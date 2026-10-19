#!/usr/bin/env bash
# Shared by the two installers. Keep version detection and rule spelling in
# one place: Hyprland 0.53 removed windowrulev2 AND renamed its effects.
# References: hyprwm/Hyprland v0.53.0 src/desktop/rule/windowRule/
# WindowRuleEffectContainer.cpp and the Hyprland wiki's Window Rules page.

hypr_version() {
  command -v hyprctl >/dev/null 2>&1 || return 0
  local out tag
  out="$(hyprctl version -j 2>/dev/null)" || out=""
  tag="$(printf '%s' "$out" | python3 -c '
import json, re, sys
try:
    data = json.load(sys.stdin)
except (ValueError, TypeError):
    data = {}
if isinstance(data, dict):
    for key in ("tag", "version"):
        value = str(data.get(key, ""))
        m = re.match(r"v?(\d+\.\d+(?:\.\d+)?)", value)
        if m:
            print(m[1])
            break
')"
  if [ -z "$tag" ]; then
    out="$(hyprctl version 2>/dev/null)" || out=""
    tag="$(printf '%s' "$out" | python3 -c '
import re, sys
text = sys.stdin.read()
m = re.search(r"(?:Hyprland\s+|tags?/v?|[Tt]ag:\s*v?)(\d+\.\d+(?:\.\d+)?)", text)
if m:
    print(m[1])
')"
  fi
  printf '%s' "$tag"
}

hypr_syntax() {
  local dir="$1" tag major minor
  tag="$(hypr_version)"
  if [ -f "$dir/hyprland.lua" ]; then
    printf 'lua'
  elif [ -z "$tag" ]; then
    # Guessing here used to silently install invalid rules. The caller must
    # ask for --syntax when hyprctl cannot identify the installed version.
    printf 'unknown'
  else
    major="${tag%%.*}"
    minor="${tag#*.}"; minor="${minor%%.*}"
    if (( major > 0 || minor >= 53 )); then printf 'v3'
    elif (( minor >= 30 )); then printf 'v2'
    else printf 'v1'; fi
  fi
}

# Usage: hypr_rules syntax class-regex name [no-focus=true]
# Shijima's Qt.Tool sprites already reject focus. Don't disable focus on its
# manager/import dialogs, which share the same WM_CLASS as the sprites.
hypr_rules() {
  local syn="$1" cls="^($2)\$" name="$3" nofocus="${4:-true}" effect
  case "$syn" in
    v1|v2)
      printf '# Managed AvA mascot rules (%s syntax).\n' "$syn"
      local prefix="windowrule" selector="$cls"
      if [ "$syn" = v2 ]; then prefix="windowrulev2"; selector="class:$cls"; fi
      for effect in float noborder noshadow noblur noanim; do
        printf '%s = %s, %s\n' "$prefix" "$effect" "$selector"
      done
      if [ "$nofocus" = true ]; then printf '%s = nofocus, %s\n' "$prefix" "$selector"; fi
      if [ "$syn" = v2 ]; then
        printf '%s = rounding 0, %s\n' "$prefix" "$selector"
        printf '%s = bordersize 0, %s\n' "$prefix" "$selector"
      fi
      ;;
    v3)
      printf '# Managed AvA mascot rules (Hyprland 0.53+ hyprlang).\n'
      for effect in 'float on' 'decorate off' 'border_size 0' 'no_shadow on' \
                    'no_blur on' 'no_anim on' 'rounding 0'; do
        printf 'windowrule = match:class %s, %s\n' "$cls" "$effect"
      done
      if [ "$nofocus" = true ]; then printf 'windowrule = match:class %s, no_focus on\n' "$cls"; fi
      ;;
    lua)
      cat <<EOF
-- Managed AvA mascot rules (Hyprland Lua config).
hl.window_rule({
  name = "$name",
  match = { class = "$cls" },
  float = true, decorate = false, border_size = 0,
  no_shadow = true, no_blur = true, no_anim = true,
  rounding = 0,
EOF
      if [ "$nofocus" = true ]; then printf '  no_focus = true,\n'; fi
      printf '})\n'
      ;;
    *) printf 'ERROR: unsupported Hyprland rule syntax: %s\n' "$syn" >&2; return 1 ;;
  esac
}

# A successful reload IPC response does not imply that the config parsed.
# Do not claim the boxes are fixed (or start more windows) if it was rejected.
hypr_reload() {
  command -v hyprctl >/dev/null 2>&1 || return 0
  local errors
  if ! hyprctl reload; then
    printf 'ERROR: Hyprland reload failed. Run hyprctl reload in your desktop session.\n' >&2
    return 1
  fi
  if errors="$(hyprctl configerrors 2>/dev/null)"; then
    if [ -n "$errors" ]; then
      printf 'ERROR: Hyprland reports configuration errors:\n%s\n' "$errors" >&2
      printf 'Fix these before restarting the mascots (hyprctl configerrors).\n' >&2
      return 1
    fi
  else
    printf 'WARNING: could not query hyprctl configerrors; check your config manually.\n' >&2
  fi
}

# POSIX shell quoting, also usable inside hyprlang's exec-once. Unlike %%q,
# this does not depend on Hyprland invoking bash rather than /bin/sh.
shell_quote() {
  python3 -c 'import shlex, sys; print(shlex.quote(sys.argv[1]), end="")' "$1"
}

lua_quote() {
  # JSON string escapes are also Lua-compatible for printable paths.
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1], ensure_ascii=False), end="")' "$1"
}

# A directly executed .desktop argument: Exec is not a shell command. Escape
# both the quoted-argument layer and the desktop-entry string/field-code layer.
desktop_quote() {
  python3 - "$1" <<'PY_DESKTOP_QUOTE'
import sys
text = sys.argv[1]
if any(ord(c) < 32 or ord(c) == 127 for c in text):
    sys.exit("cannot put a path containing control characters in an autostart entry")
for char in ('\\', '"', '$', '`'):
    text = text.replace(char, '\\' + char)
text = text.replace('\\', '\\\\').replace('%', '%%')
print('"' + text + '"', end='')
PY_DESKTOP_QUOTE
}
