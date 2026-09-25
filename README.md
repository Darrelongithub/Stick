# Stick — AvA Shimeji 4-Pack (Blue / Orange / Yellow / Green)

Animation vs Animator style desktop buddies for **Shijima-Qt** (and Shimeji-ee)
on Linux, with a batch of brand-new crisp animations generated in the pack's
exact art style (128×128, feet anchored at 64,128, hard pixel edges like the
originals).

This repo was trimmed down to the core four. Purple, Red, TCO, TDL and victim
were removed.

## New animations (266 frames)

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
| Backflip | Crouch, jump, full backward rotation, stuck landing |
| SnackTime | Munches an apple (visible bite + crumbs) |
| PowerSlide | Sprint slide with dust and speed lines |
| PushUps | Full plank push-up reps |
| Sneeze | Big inhale… ACHOO spray |
| PaperPlane | Folds? No — throws a paper plane that soars off |

Signatures (one per character, AvA canon):

| Character | Signature |
|---|---|
| 🟠 Orange | **DrawAlive** — draws a star that pops to life with sparkles |
| 🟡 Yellow | **Tinker** — redstone tinkering with wrench + spark bursts |
| 🔵 Blue | **BrewPotion** — holds up a bubbling potion |
| 🟢 Green | **PlayGuitar** — guitar solo with floating notes |

All actions are already wired into each character's `conf/actions.xml` and
`conf/behaviors.xml` — just install and they happen automatically.

## Install

### Shijima-Qt (recommended — works on Linux, no Java needed)

Shijima-Qt is a modern cross-platform shimeji app. It imports character packs
from zip archives.

```bash
git clone <this-repo> && cd Stick
pip install pillow                          # only if regenerating frames
python3 tools/build_shijima.py              # builds per-character zips
python3 tools/build_shijima.py --all        # builds per-char + full pack zip
```

This creates ready-to-import zips in `dist/shijima/`:

| File | What's inside |
|---|---|
| `AvA_Blue.zip` | Blue character (images + conf/) |
| `AvA_Orange.zip` | Orange character |
| `AvA_Yellow.zip` | Yellow character |
| `AvA_Green.zip` | Green character |
| `AvA_Stick_Pack.zip` | All four in standard `img/` layout |

**To import:**

1. Open Shijima-Qt
2. Drag & drop any zip file(s) into the app window
3. Click **Add** to spawn them on your desktop

If importing a single character zip doesn't work, try the full pack zip
(`AvA_Stick_Pack.zip`) instead — it uses the standard `img/CharacterName/`
layout that Shijima-Qt expects.

### Shimeji-ee (Java, legacy)

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

## Troubleshooting

Shimeji-ee failing to load a character? These are the classic errors:

| Error / symptom | Cause & fix |
|---|---|
| `duplicate action found: <name>` | The same action defined twice in `conf/actions.xml` (an old version of `patch_xml.py` inserted into both `<ActionList>` sections). Fixed in this repo; check any copy with `python3 tools/validate.py`. |
| `no corresponding action <name>` | A `Behavior` whose `Name` doesn't match any action — Shimeji-ee resolves a behavior's action by the behavior's own `Name`, and an `<ActionReference>` child is not valid inside `<Behavior>`. Run `python3 tools/repair_xml.py` (one-time fix), then `python3 tools/validate.py`. |
| `NoClassDefFoundError: NimRODTheme` | Shimeji-ee's jar manifest expects its bundled jars under `lib/`, but some extractions dump them into the Shimeji-ee root. `install.sh` now copies `jna.jar`, `examples.jar`, `AbsoluteLayout.jar` and `nimrodlf.jar` into `lib/` automatically; by hand: move those four jars from the root into `lib/`. |
| `HeadlessException` on startup | Your `java` is a headless JRE (e.g. Fedora's `java-NN-openjdk-headless`). Install a full JRE instead: Fedora `sudo dnf install java-<version>-openjdk` (not `-headless`), Debian/Ubuntu `default-jre` (not `-headless`). `install.sh` warns about this. |

Notes:

* **GNOME/Wayland:** Java runs through XWayland there, so shimejis may
  glitch — black boxes instead of sprites, or no interaction with native
  Wayland windows. Log into an X11 session for fully correct behavior.
* **Shijima-Qt:** Use `python3 tools/build_shijima.py --all` to create
  import-ready zips. Drag & drop into the Shijima-Qt app window. See the
  [Install](#shijima-qt-recommended--works-on-linux-no-java-needed) section
  above for details.
* **Shijima-Qt says "successful" but nothing appears?** Make sure you import
  a zip file (not the raw repo folder). The zip must contain a character
  folder with PNG images and a `conf/` subfolder. Try `AvA_Stick_Pack.zip`
  (the full pack zip) if the per-character zips don't work.

## Regenerating / making more

Frames are procedural — tweak poses in `tools/stickgen.py`, then:

```bash
pip install pillow
python3 tools/stickgen.py                 # renders all chars into AVA Shimejis/
python3 tools/patch_xml.py                # (re)wires actions.xml + behaviors.xml
python3 tools/validate.py                 # sanity-checks all four characters
python3 tools/build_shijima.py --all      # builds import-ready zips for Shijima-Qt
```

Preview contact sheets land in `preview/new/`. The patch script is idempotent
(running it twice won't duplicate entries). If you ever meet XMLs patched by
the old buggy version of the script, `python3 tools/repair_xml.py` fixes them
in place.

## Layout

```
AVA Shimejis/{Blue,Orange,Yellow,Green}/  image sets + per-character conf/
tools/stickgen.py      frame generator (poses, props, fx)
tools/patch_xml.py     XML wiring for new actions/behaviors
tools/repair_xml.py    one-time repair for XMLs damaged by the old patcher
tools/validate.py      validates actions/behaviors/images for all characters
tools/build_shijima.py builds import-ready zips for Shijima-Qt
linux/install.sh       installer: image sets + toggle + autostart
linux/ava-toggle.sh    on/off toggle with desktop notification
```

Made with the generator in this repo — every pixel reproducible. Have fun! 🧡💛💙💚
