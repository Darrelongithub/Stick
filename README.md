# Stick — AvA Shimeji 4-Pack (Blue / Orange / Yellow / Green)

Animation vs Animator style desktop buddies for **Shimeji-ee on Linux**, with a
batch of brand-new crisp animations generated in the pack's exact art style
(128×128, feet anchored at 64,128, supersampled for clean edges).

This repo was trimmed down to the core four. Purple, Red, TCO, TDL and victim
were removed.

## New animations (166 frames)

Shared by all four:

| Action | What it looks like |
|---|---|
| Wave | Friendly hello wave |
| Cheer | Crouch, leap, arms up in a V |
| FightCombo | Bounce, jab, cross, kick, block |
| SwordPractice | Idle, raise, two slashes with arcs |
| Mine | Pickaxe raise, strike, impact burst (Minecraft!) |
| Sleep | Lying down with rising Zzz |
| Hurt | Knocked flat with dizzy stars, wobbly getup |
| CursorSlash | Leaps at your cursor with a huge slash (triggers near the cursor) |
| GlitchOut | Slice-displaced "surviving deletion" flicker |
| BattleRage | Full sequence: fists → sword → cursor slash |

Signatures (one per character, AvA canon):

| Character | Signature |
|---|---|
| 🟠 Orange | **DrawAlive** — draws a star that pops to life with sparkles |
| 🟡 Yellow | **Tinker** — redstone tinkering with wrench + spark bursts |
| 🔵 Blue | **BrewPotion** — holds up a bubbling potion |
| 🟢 Green | **PlayGuitar** — guitar solo with floating notes |

All actions are already wired into each character's `conf/actions.xml` and
`conf/behaviors.xml` — just install and they happen automatically.

## Install (Linux)

```bash
git clone <this-repo> && cd Stick
./linux/install.sh            # auto-finds ~/Shimeji-ee (or pass the path)
./linux/install.sh ~/my-shimeji --replace   # also stash other sets into img/unused
```

What it does:

1. Copies `Blue/ Orange/ Yellow/ Green/` (images + their own `conf/`) into
   Shimeji-ee's `img/` folder.
2. Installs `ava-toggle.sh` next to the jar for on/off control.
3. Installs a `~/.config/autostart/ava-shimeji.desktop` entry so they
   **always start on boot/login** — even if you toggled them off and forgot.

## On/off toggle

```bash
~/Shimeji-ee/ava-toggle.sh     # stop if running, start if stopped (+ notification)
```

Tip: bind that script to a hotkey (GNOME: Settings → Keyboard → Custom
Shortcut, KDE: Custom Shortcuts). To stop them starting on boot, delete
`~/.config/autostart/ava-shimeji.desktop`.

## Regenerating / making more

Frames are procedural — tweak poses in `tools/stickgen.py`, then:

```bash
pip install pillow
python3 tools/stickgen.py                 # renders all chars into AVA Shimejis/
python3 tools/patch_xml.py                # (re)wires actions.xml + behaviors.xml
```

Preview contact sheets land in `preview/new/`. The patch script is idempotent
(running it twice won't duplicate entries).

## Layout

```
AVA Shimejis/{Blue,Orange,Yellow,Green}/  image sets + per-character conf/
tools/stickgen.py      frame generator (poses, props, fx)
tools/patch_xml.py     XML wiring for new actions/behaviors
linux/install.sh       installer: image sets + toggle + autostart
linux/ava-toggle.sh    on/off toggle with desktop notification
```

Made with the generator in this repo — every pixel reproducible. Have fun! 🧡💛💙💚
