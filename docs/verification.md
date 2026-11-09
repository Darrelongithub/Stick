# Verification report

Date: 2026-11-08 (sandbox clock reported 2026-11-09 during the run).

## Pack / XML / frames

```bash
python3 tools/patch_xml.py
python3 tools/validate.py
python3 -m pytest -q
python3 runner/ava_runner.py --simulate 5000 --seed 7
python3 tools/normalize_stock_art.py --check
python3 tools/review_animations.py
python3 tools/make_docs.py
```

Results:

- `validate.py`: **OK — 4 characters, 1844 pose references, 46 generated
  actions, 2 sequences** (Shimeji-ee and Shijima-Qt).
- `pytest`: **56 passed, 6294 subtests passed**.
- Python runner simulation (200 s, seed 7): **0 simultaneous active animations,
  0 inactive-character translation**, 45 completed turns per character.
- `normalize_stock_art.py --check`: Orange/Yellow/Green original-pack art is
  **1.000×** the shared original; **0 files would change**.
- Animation audit: **62 pose-bearing named actions** reviewed; contact sheets
  `docs/animation-review-*.png`, table `docs/animation-audit.md`.
  - 54 KEEP, 8 REPAIR flags. The REPAIR flags are legacy stock/menu frames whose
    art touches the canvas edge (hug/pinch/sit/bounce families). They are not
    part of the autonomous reference repertoire; they remain for required host
    interactions and are documented rather than silently redrawn.

## ShimeLinux native turn coordinator

Patch: `linux/shimelinux/shimelinux-turns.patch`, pinned to upstream
`b131465f5af478347009bcf6b29bad6f5579af85`.

- Fresh clone apply + reverse-apply: **OK**.
- Standalone coordinator JVM tests: **6 passed** (FIFO across owners/types,
  stale/foreign completion rejection, multiple explicit requests, removal,
  released-before-start drag, failed initialization).
- Headless core playback harness (`linux/shimelinux/HostPlaybackHarness.kt`):

```text
LOADED Blue: 82 behaviors
LOADED Orange: 82 behaviors
LOADED Yellow: 82 behaviors
LOADED Green: 82 behaviors
NATIVE CORE: 1200 ticks, 22 completed, 10 cancelled; overlaps=0 idleMovement=0 pauseViolations=0
```

The harness compiles the real upstream action/animation/config/environment/
hotspot/image classes plus the patched Manager/Mascot/UserBehavior/
TurnCoordinator/StationaryIdle. It replaces only the desktop shell, native
window, debug window and Nashorn evaluator with headless test adapters. It
exercises natural successors, drag/release, a queued drag released before grant,
the menu `setBehaviorAll("ChaseMouse")` path, pause, and disposal.

Composite preview: `preview/native/native-playback.mp4` (ignored) and
`docs/native-playback.png`.

### Limits / not verified here

- **No full ShimeLinux Gradle build** in this sandbox (no JDK 21 build tools /
  Gradle / Maven access). The patch applies cleanly and the playback core
  compiles/runs headlessly, but `./gradlew jar` still needs a normal build
  environment.
- **No real Hyprland/GNOME/KDE window smoke test.** Native window shaping,
  compositor rules, and tray/menu rendering are unchanged upstream code and
  were not exercised on a desktop.
- The headless script bridge approximates Nashorn variable binding for stock
  XML expressions; production ShimeLinux keeps Nashorn.

## Orange / head-style decision

The autonomous reference repertoire (walk, run, dance, jump, crawl, climb,
fall, hobbies, fights, etc.) is generated **hollow-headed** reference art at one
figure scale. Required host interactions and menu compatibility paths may still
use the pack's **filled-head stock** frames (stand, pinch, hug, sit, bounce).
`normalize_stock_art.py` is a *scale* repair for legacy stock art, not a
head-style conversion; its stale `Dance` anchor rewrite was removed because
Dance is now generated 160×160 reference art. `--check` reports no scale drift
and changes nothing.
