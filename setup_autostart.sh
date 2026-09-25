#!/bin/bash
# AvA Stickman Pack - Quick setup for auto-start + kill hotkey
# Run: bash setup_autostart.sh

set -e

echo "=== AvA Stickman Setup ==="

# 1. Find shijima-qt
SHIJIMA=""
for cmd in shijima-qt shijima; do
    if command -v "$cmd" &>/dev/null; then
        SHIJIMA="$(command -v "$cmd)"
        break
    fi
done
if [ -z "$SHIJIMA" ]; then
    # Try common locations
    for p in ~/Applications/Shijima*/shijima-qt \
             /opt/Shijima*/shijima-qt \
             /usr/bin/shijima-qt \
             ~/.local/bin/shijima-qt \
             ~/Downloads/Shijima*/shijima-qt; do
        if [ -x "$p" ]; then
            SHIJIMA="$p"
            break
        fi
    done
fi

if [ -z "$SHIJIMA" ]; then
    echo "Could not find shijima-qt. Enter the full path:"
    read -r SHIJIMA
    [ ! -x "$SHIJIMA" ] && echo "Not found or not executable: $SHIJIMA" && exit 1
fi
echo "Found: $SHIJIMA"

# 2. Create autostart entry
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/shijima.desktop << DESKTOP
[Desktop Entry]
Type=Application
Name=Shijima-Qt (Desktop Pets)
Exec=$SHIJIMA
X-GNOME-Autostart-enabled=true
DESKTOP
echo "✓ Auto-start on login: ~/.config/autostart/shijima.desktop"

# 3. Create kill script
cat > ~/.local/bin/kill-stickmen << 'KILL'
#!/bin/bash
pkill -f "shijima" 2>/dev/null && notify-send "Stickmen killed" || echo "No stickmen running"
KILL
chmod +x ~/.local/bin/kill-stickmen
echo "✓ Kill script: ~/.local/bin/kill-stickmen"

# 4. Create restart script
cat > ~/.local/bin/restart-stickmen << RESTART
#!/bin/bash
pkill -f "shijima" 2>/dev/null
sleep 0.5
$SHIJIMA &disown
notify-send "Stickmen restarted"
RESTART
chmod +x ~/.local/bin/restart-stickmen
echo "✓ Restart script: ~/.local/bin/restart-stickmen"

echo ""
echo "=== Set up keyboard shortcuts ==="
echo ""
echo "  GNOME: Settings → Keyboard → Custom Shortcuts:"
echo "    Kill stickmen:    ~/.local/bin/kill-stickmen    (Ctrl+Alt+K)"
echo "    Restart stickmen: ~/.local/bin/restart-stickmen (Ctrl+Alt+Shift+K)"
echo ""
echo "  KDE: System Settings → Shortcuts → Custom Shortcuts"
echo "    Same commands as above"
echo ""
echo "Done! Log out and back in to test auto-start."