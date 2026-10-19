#!/usr/bin/env bash
# Install the AvA 4-pack (Blue/Orange/Yellow/Green) into Shimeji-ee on Linux,
# plus autostart-on-boot and an on/off toggle script.
#
# Usage:
#   ./install.sh [path-to-shimeji-folder] [--replace]
#   --replace : stash any other image sets into img/unused (only the AvA 4 run)
set -u

RUN_TIMEOUT=10   # seconds; a wedged JRE must never hang the installer

REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/linux/hyprland-common.sh"

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  echo "Usage: $0 [path-to-shimeji-folder] [--replace] [--no-hyprland]"
  echo "  --replace     : move any other image sets into img/unused"
  echo "  --no-hyprland : skip the Hyprland window rules + autostart step"
}

# Run a command under a wall-clock cap. `timeout` is not everywhere
# (busybox, macOS); without it, run uncapped rather than failing the install.
run_capped() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$RUN_TIMEOUT" "$@"
  else
    "$@"
  fi
}

# Reject paths carrying control characters (0x00-0x1F, 0x7F). They cannot be
# represented in a .desktop Exec value at all, and a newline would let the
# path inject whole keys - a second Exec= included - into a file that runs at
# every login. Printable ASCII and UTF-8 (bytes >= 0x80) are fine.
path_is_printable() {
  # Count the control bytes rather than capturing them: $(...) would strip a
  # trailing newline, which is exactly the character we must not miss.
  [ "$(printf '%s' "$1" | LC_ALL=C tr -cd '\000-\037\177' | wc -c | tr -d ' ')" -eq 0 ]
}

# ---------------- arguments ----------------
TARGET=""
REPLACE=false
SKIP_HYPRLAND=false
for arg in "$@"; do
  case "$arg" in
    --replace) REPLACE=true ;;
    --no-hyprland) SKIP_HYPRLAND=true ;;
    --hyprland) SKIP_HYPRLAND=false ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option: $arg" ;;
    *) if [ -z "$TARGET" ]; then TARGET="$arg"; else die "unexpected argument: $arg"; fi ;;
  esac
done

if [ -z "$TARGET" ]; then
  for d in "$HOME/Shimeji-ee" "$HOME/shimeji-ee" "$HOME/Shimeji" "/opt/shimeji-ee" "/opt/Shimeji-ee"; do
    [ -d "$d" ] && TARGET="$d" && break
  done
fi
if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
  echo "Could not find your Shimeji-ee folder. Run: ./install.sh /path/to/shimeji [--replace]"
  exit 1
fi
path_is_printable "$TARGET" || die \
  "the Shimeji folder path contains control characters (newline, tab, ...); it cannot be put in an autostart entry safely - move the folder and retry"
TARGET="$(cd "$TARGET" && pwd -P)"
echo "Shimeji folder: $TARGET"

command -v java >/dev/null || { echo "Java not found - install a JRE first (Fedora: sudo dnf install java-latest-openjdk)"; exit 1; }
JAR=""
for candidate in "$TARGET/Shimeji-ee.jar" "$TARGET/Shimeji.jar" "$TARGET"/*himeji*.jar; do
  if [ -f "$candidate" ]; then JAR="$candidate"; break; fi
done
[ -n "${JAR:-}" ] || { echo "No Shimeji jar found in $TARGET"; exit 1; }
path_is_printable "$JAR" || die \
  "the jar path contains control characters; it cannot be put in an autostart entry safely - rename the jar and retry"
echo "Found: $JAR"

# 0a. Fix flat jar extractions BEFORE installing: Shimeji-ee's manifest
# Class-Path is ./lib/jna.jar ./lib/examples.jar ./lib/AbsoluteLayout.jar
# ./lib/nimrodlf.jar, but some archive tools dump those jars into the
# Shimeji-ee root and leave lib/ missing/empty -> NoClassDefFoundError
# NimRODTheme on startup.
for j in jna.jar examples.jar AbsoluteLayout.jar nimrodlf.jar; do
  if [ ! -f "$TARGET/lib/$j" ] && [ -f "$TARGET/$j" ]; then
    mkdir -p "$TARGET/lib" || die "cannot create $TARGET/lib"
    cp -p "$TARGET/$j" "$TARGET/lib/$j" || die "cannot copy $j into $TARGET/lib"
    echo "Fixed jar layout: copied $j from the Shimeji-ee root into lib/"
  fi
done
for j in jna.jar examples.jar AbsoluteLayout.jar nimrodlf.jar; do
  if [ ! -f "$TARGET/lib/$j" ]; then
    echo "WARNING: lib/$j not found anywhere - Shimeji-ee may fail to start" \
         "with NoClassDefFoundError. Re-extract your Shimeji-ee download" \
         "so its lib/ folder is populated." >&2
  fi
done

# 0b. Warn (non-fatal) if the resolved java has no GUI support: headless
# JREs (e.g. Fedora's java-NN-openjdk-headless) throw HeadlessException.
# Both probes are capped: a hung JRE (or a stale mount under JAVA_HOME)
# must not wedge the installer forever - we just warn less specifically.
JAVA_BIN="$(command -v java)"
JAVA_HOME_DIR="$(dirname "$(dirname "$(readlink -f "$JAVA_BIN" 2>/dev/null || echo "$JAVA_BIN")")")"
if ! run_capped find "$JAVA_HOME_DIR" -name libawt_xawt.so -print -quit 2>/dev/null | grep -q .; then
  JAVA_VER="$(run_capped "$JAVA_BIN" -version 2>&1 | head -n 1 | sed -e 's/.*version "//' -e 's/".*//' -e 's/^1\.//' -e 's/[._].*//')"
  echo "WARNING: $JAVA_BIN looks like a headless JRE (no libawt_xawt.so under $JAVA_HOME_DIR)." >&2
  echo "         Shimeji-ee needs GUI support; expect HeadlessException otherwise." >&2
  if [ -n "${JAVA_VER:-}" ]; then
    echo "         Fedora:       sudo dnf install java-$JAVA_VER-openjdk   (not -headless)" >&2
  else
    echo "         Fedora:       sudo dnf install java-<version>-openjdk  (not -headless)" >&2
  fi
  echo "         Debian/Ubuntu: install default-jre                     (not -headless)" >&2
fi

# Stop before changing files: a running JVM can save stale settings on exit.
# Install the new controller first so even instances started with a relative
# jar path are found, and concurrent autostarts are serialized.
cp "$REPO/linux/ava-toggle.sh" "$TARGET/ava-toggle.sh" || die "cannot install the launcher"
chmod +x "$TARGET/ava-toggle.sh" || die "cannot make the launcher executable"
"$TARGET/ava-toggle.sh" --stop || die "could not stop Shimeji-ee before installing"

# 1. image sets (each folder carries its own conf/actions.xml + behaviors.xml)
mkdir -p "$TARGET/img/unused" || die "cannot create $TARGET/img/unused (is $TARGET writable?)"
for c in Blue Orange Yellow Green; do
  rm -rf "$TARGET/img/$c" || die "cannot replace $TARGET/img/$c"
  cp -r "$REPO/AVA Shimejis/$c" "$TARGET/img/$c" || die "cannot copy the $c image set into $TARGET/img (is $TARGET writable?)"
  [ -f "$TARGET/img/$c/conf/actions.xml" ] || die "the $c image set landed incomplete in $TARGET/img/$c"
  echo "Installed image set: $c"
done
if $REPLACE; then
  for d in "$TARGET"/img/*/; do
    [ -d "$d" ] || continue
    n="$(basename "$d")"
    case "$n" in Blue|Orange|Yellow|Green|unused) ;; *)
      mv "$d" "$TARGET/img/unused/$n" || die "cannot stash $n into img/unused"
      echo "Stashed old set: $n -> img/unused" ;;
    esac
  done
fi

# 2. Apply the same repair as the standalone Hyprland script, including
# duplicate property keys and a missing conf/ folder.
python3 "$REPO/linux/configure-mascots.py" shimeji "$TARGET" || die "cannot disable multiplication"
echo "Installed guarded launcher: $TARGET/ava-toggle.sh"

# 3. autostart on boot/login - ALWAYS starts them, even if toggled off earlier
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$AUTOSTART_DIR" || die "cannot create $AUTOSTART_DIR"
DESKTOP="$AUTOSTART_DIR/ava-shimeji.desktop"
EXEC_LAUNCHER="$(desktop_quote "$TARGET/ava-toggle.sh")" || die "cannot quote the launcher path"
# printf '%s' (not a here-doc): an unquoted here-doc would eat the backslashes
# that desktop_quote just added.
printf '%s\n' \
  "[Desktop Entry]" \
  "Type=Application" \
  "Name=AvA Shimejis" \
  "Comment=Start the Animation vs Animator desktop buddies" \
  "Exec=$EXEC_LAUNCHER --start" \
  "Terminal=false" \
  "NotShowIn=Hyprland;" \
  "X-GNOME-Autostart-enabled=true" > "$DESKTOP" || die "cannot write $DESKTOP"
[ -s "$DESKTOP" ] || die "wrote an empty $DESKTOP"
echo "Installed autostart: ~/.config/autostart/ava-shimeji.desktop"
echo "  (read by GNOME, KDE, XFCE... - NOT by Hyprland, which has no XDG"
echo "   autostart support; the Hyprland step below handles that case)"

# 4. Hyprland: window rules (no more boxes) + real autostart.  Hyprland tiles
# every window Shimeji-ee opens and draws a border around it, and it ignores
# ~/.config/autostart entirely, so this step is what makes the pack usable
# there.  Skipped with --no-hyprland, and a no-op elsewhere.
IS_HYPR=false
if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
  IS_HYPR=true
elif [ -n "${XDG_CURRENT_DESKTOP:-}" ]; then
  case "$XDG_CURRENT_DESKTOP" in *[Hh]yprland*) IS_HYPR=true ;; esac
elif [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/hypr/hyprland.conf" ] || [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/hypr/hyprland.lua" ]; then
  IS_HYPR=true
fi
if ! $SKIP_HYPRLAND && $IS_HYPR; then
  echo
  echo "Hyprland detected - setting up window rules and autostart:"
  if bash "$REPO/linux/hyprland.sh" "$TARGET" --no-start; then
    :
  else
    die "the Hyprland step failed; fix the reported errors and re-run: $REPO/linux/hyprland.sh \"$TARGET\""
  fi
fi

echo
echo "Done! Start the repaired crew (the old instances have been stopped):"
echo "  \"$TARGET/ava-toggle.sh\" --start"
echo "Use --stop to clear the screen, --restart to reset to four, or no option to toggle."
echo "They will also auto-start on every boot."
echo "Tip: bind ava-toggle.sh to a hotkey in your desktop's Keyboard settings."
echo
echo "Rather stay on Shijima-Qt? This same pack works there:"
echo "  $REPO/linux/shijima.sh --install --autostart"
