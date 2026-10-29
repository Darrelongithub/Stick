#!/usr/bin/env python3
"""AvA Shimejis runner - the four characters as ONE small Qt process.

No Java (Shimeji-ee) and no Shijima-Qt.  Why it exists:

* Shijima-Qt is archived upstream, does not autostart on Hyprland, and does
  per-paint work that makes several mascots feel laggy: every repaint
  rebuilds a QBitmap mask and calls setMask().  Here the masks are built once
  per frame *change* (they are cached), and a single timer drives all four
  characters.
* Shimeji-ee needs a JVM per session.  This runner is a few MB of Python.

Usage
    python3 runner/ava_runner.py                 # run on the desktop
    python3 runner/ava_runner.py --simulate 900  # 36 s of scheduling, no GUI

Needs PySide6 for the desktop part; --simulate needs nothing beyond the
standard library.

The pack is read from ``conf/actions.xml`` of each character (see pack.py), so
it always runs whatever art is in the repo.
"""
from __future__ import annotations

import argparse
import collections
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pack  # noqa: E402

TICK_MS = 40                     # Shimeji-ee tick; one pose Duration unit
RENDER_HZ = 60                   # position updates are interpolated at 60 Hz
RENDER_MS = 1000.0 / RENDER_HZ
CHARS = ["Blue", "Orange", "Yellow", "Green"]
DEFAULT_PACK = os.path.join(ROOT, "AVA Shimejis")

# Internal/reactive actions and duplicate aliases are not autonomous activities.
# Most importantly, Stand and all one-frame Stay poses are absent: Idle is the
# animated breathing replacement, so the runner never chooses a ten-second
# statue as entertainment.
EXCLUDE = {
    "Stand", "Sit", "SitAndLookUp", "SitAndLookAtMouse", "SitWithLegsUp",
    "SitWithLegsDown", "Falling", "Fall", "Dragged", "Thrown", "Pinched",
    "Resisting", "Offset", "Dash", "Tripping", "StandFromFloor",
}
LOCOMOTION = {"Walk", "Run"}
FALLBACK_WEIGHTS = {"Idle": 8, "Walk": 18, "Run": 12, "Sleep": 8,
                    "Meditate": 8, "Crawl": 14}


def floor_actions(ch):
    """Animated floor actions a character may start on its own."""
    pool = []
    for name, act in ch.actions.items():
        if not act.poses or name in EXCLUDE:
            continue
        if act.kind not in ("Animate", "Move"):
            continue
        if (act.border or "Floor") != "Floor":
            continue
        if len(set(act.images)) < 2:          # never schedule a static pose
            continue
        # Primitive actions such as Hurt's recovery helpers have no selectable
        # behaviour. Walk/Run are the two intentional exceptions: stock host
        # behaviours target them from movement sequences.
        if ch.frequencies and name not in ch.frequencies and name not in LOCOMOTION:
            continue
        pool.append(act)
    return pool


def action_weight(ch, action):
    """Use the pack's per-character personality weight in the local runner."""
    if action.name in ch.frequencies:
        return max(1, ch.frequencies[action.name])
    if action.name == "Walk":
        return max(1, ch.frequencies.get("WalkAlongWorkAreaFloor", 18))
    if action.name == "Run":
        return max(1, ch.frequencies.get("RunAlongWorkAreaFloor", 12))
    return FALLBACK_WEIGHTS.get(action.name, 1)


def visual_key(action):
    """Animation identity independent of colour, alias, or cycle phase."""
    names = tuple(os.path.basename(name) for name in action.images)
    # Cyclic XML is quarter-phase shifted per character. Canonicalize rotations
    # so Crawl still reserves one shared visual even when Blue starts at 01 and
    # Orange starts at 05.
    return min(names[i:] + names[:i] for i in range(len(names)))


class ActionCoordinator:
    """Reserve visual actions across the crew and enforce short cooldowns."""

    def __init__(self):
        self.active = {}
        self.global_recent = collections.deque(maxlen=4)

    def choose(self, owner, pool, weights, rng, recent):
        # The owner's old action no longer needs to reserve its slot.
        self.active.pop(owner, None)
        busy = set(self.active.values())
        recent = set(recent)

        def candidates(avoid_recent=True, avoid_global=True):
            out = []
            for action, weight in zip(pool, weights):
                key = visual_key(action)
                if key in busy or (avoid_recent and key in recent):
                    continue
                if avoid_global and key in self.global_recent:
                    continue
                out.append((action, weight))
            return out

        choices = (candidates() or candidates(avoid_global=False)
                   or candidates(avoid_recent=False, avoid_global=False))
        if not choices:
            # Only possible for a tiny custom pack with fewer distinct actions
            # than mascots; degrade gracefully rather than stopping the runner.
            choices = list(zip(pool, weights))
        action = rng.choices([a for a, _w in choices],
                             [w for _a, w in choices])[0]
        key = visual_key(action)
        self.active[owner] = key
        self.global_recent.append(key)
        return action


class Mascot:
    """Scheduling and position for one character.  No drawing in here."""

    def __init__(self, ch, rng, x, screen_w, frame_w=None, coordinator=None):
        self.ch = ch
        self.name = ch.name
        self.rng = rng
        self.pool = floor_actions(ch)
        if not self.pool:
            raise ValueError(f"{ch.name}: no animated floor actions to play")
        self.weights = [action_weight(ch, a) for a in self.pool]
        self.coordinator = coordinator
        self.recent = collections.deque(maxlen=4)
        self.screen_w = screen_w
        self.x = float(x)                      # anchor x on screen
        self.look_right = False
        self.action = None
        self.index = 0
        self.left = 0
        self.pose = None
        self.dirty = False                     # frame changed since last draw
        self.frame_w = frame_w or (lambda _pose: 160)
        self.started = collections.Counter()
        self._start_next()

    # -- scheduling -------------------------------------------------------
    def _start_next(self):
        if self.action is not None:
            self.recent.append(visual_key(self.action))
        if self.coordinator:
            self.action = self.coordinator.choose(
                self, self.pool, self.weights, self.rng, self.recent)
        else:
            choices = [(a, w) for a, w in zip(self.pool, self.weights)
                       if visual_key(a) not in self.recent]
            choices = choices or list(zip(self.pool, self.weights))
            self.action = self.rng.choices([a for a, _w in choices],
                                           [w for _a, w in choices])[0]
        self.started[self.action.name] += 1
        self.index = 0
        self.pose = self.action.poses[0]
        self.left = self.pose.duration
        moving = any(p.velocity[0] for p in self.action.poses)
        if moving:
            # walk away from the nearer wall, otherwise pick at random
            if self.x < self.screen_w * 0.2:
                self.look_right = True
            elif self.x > self.screen_w * 0.8:
                self.look_right = False
            else:
                self.look_right = self.rng.random() < 0.5
        self.dirty = True

    def advance(self, ticks):
        """Advance a fractional number of 40ms ticks.

        Frame boundaries remain faithful to the XML, while velocity is applied
        proportionally on each 60Hz render update.  A stock run therefore moves
        in ~3px visual increments rather than 8-18px jumps.
        """
        ticks = max(0.0, float(ticks))
        while ticks > 1e-9:
            chunk = min(ticks, float(self.left))
            dx = self.pose.velocity[0] * (-1 if self.look_right else 1) * chunk
            if dx:
                target = self.x + dx
                new_x = min(max(target, 0.0), float(self.screen_w))
                if abs(new_x - target) > 1e-9:  # hit edge: finish this action
                    self.left = 0
                self.x = new_x
            self.left -= chunk
            ticks -= chunk
            if self.left > 1e-9:
                continue
            self.index += 1
            if self.index >= len(self.action.poses):
                self._start_next()
            else:
                self.pose = self.action.poses[self.index]
                self.left = self.pose.duration
                self.dirty = True

    def step(self):
        """Advance one logical host tick (headless simulation compatibility)."""
        self.advance(1.0)

    # -- drawing helpers --------------------------------------------------
    def anchor_on_window(self):
        """Window top-left (x, y offset from the anchor) for the current frame."""
        ax, ay = self.pose.anchor
        if self.look_right:
            ax = self.frame_w(self.pose) - ax
        return ax, ay


def simulate(args, chars):
    master = random.Random(args.seed)
    coordinator = ActionCoordinator()
    mascots = []
    for c in chars:
        rng = random.Random(master.getrandbits(64))
        mascots.append(Mascot(c, rng, master.uniform(0, args.screen_w),
                              args.screen_w, coordinator=coordinator))
    out_of_bounds = 0
    simultaneous_duplicates = 0
    frame_changes = [0] * len(mascots)
    for _ in range(args.simulate):
        for i, m in enumerate(mascots):
            m.dirty = False
            m.step()
            if m.dirty:
                frame_changes[i] += 1
            if not (0 <= m.x <= args.screen_w):
                out_of_bounds += 1
        keys = [visual_key(m.action) for m in mascots]
        simultaneous_duplicates += len(keys) - len(set(keys))
    seconds = args.simulate * TICK_MS / 1000
    print(f"simulated {seconds:.0f}s of {len(mascots)} characters "
          f"({args.simulate} ticks x {TICK_MS} ms)")
    for m, changes in zip(mascots, frame_changes):
        top = ", ".join(f"{n} x{c}" for n, c in m.started.most_common(4))
        print(f"  {m.name:7s} {changes / seconds:5.1f} frame changes/s "
              f"| {sum(m.started.values())} actions | {top}")
    print(f"out-of-bounds positions: {out_of_bounds}")
    print(f"simultaneous duplicate animations: {simultaneous_duplicates}")
    return 0 if out_of_bounds == 0 and simultaneous_duplicates == 0 else 1


def prepare_desktop():
    # Native Wayland does not allow QWidget.move() or X11 shape masks. Fedora
    # commonly defaults Qt to Wayland, even though these are desktop sprites,
    # not ordinary application windows. Use XWayland for this runner only.
    if sys.platform.startswith("linux") and (
            os.environ.get("WAYLAND_DISPLAY") or
            os.environ.get("XDG_SESSION_TYPE") == "wayland" or
            os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")):
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("XWayland is required (DISPLAY is unset). On Fedora install "
                               "xorg-x11-server-Xwayland and enable XWayland in Hyprland.")
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def run_desktop(args, chars):
    try:
        prepare_desktop()
    except RuntimeError as exc:
        print(f"ava-runner: {exc}", file=sys.stderr)
        return 2
    try:
        from PySide6.QtCore import QElapsedTimer, QLockFile, Qt, QTimer
        from PySide6.QtGui import QBitmap, QGuiApplication, QImage, QPainter, QPixmap, QRegion
        from PySide6.QtWidgets import QApplication, QWidget
    except ImportError as exc:
        sys.stderr.write(f"ava-runner: the desktop part could not start: {exc}\n"
                         "  needs PySide6 plus the system OpenGL/xkb libraries:\n"
                         "    pip install PySide6-Essentials\n"
                         "    Debian/Ubuntu: libgl1 libegl1 libxkbcommon0 libfontconfig1\n"
                         "    Fedora: mesa-libGL mesa-libEGL libxkbcommon libxcb xcb-util-cursor\n"
                         "    Arch: mesa libxkbcommon fontconfig\n"
                         "  (--simulate needs none of this)\n")
        return 2

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # One runner at a time, however it was started (systemd, Hyprland, by hand).
    cache = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    # Preserve the existing per-session lock path when upgrading a live runner.
    lock_dir = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(cache, "ava-shimeji")
    os.makedirs(lock_dir, mode=0o700, exist_ok=True)
    lock = QLockFile(os.path.join(lock_dir, "ava-runner.lock"))
    if not lock.tryLock(100):
        print("ava-runner: already running", file=sys.stderr)
        return 75                       # EX_TEMPFAIL: systemd does not restart on it

    geo = QGuiApplication.primaryScreen().availableGeometry()
    # Qt positions are global, and the primary screen need not start at x=0.
    # Mascot coordinates are local to that screen; add the offset back when placing.
    floor_y = geo.bottom() - args.floor_margin
    screen_left = geo.left()
    screen_w = geo.width()

    # Decode every frame once.  Frames are QImages; the Qt paint path only
    # ever draws cached pixmaps.
    images = {}
    for ch in chars:
        for act in ch.actions.values():
            for pose in act.poses:
                path = ch.locate(pose.image)
                if path not in images:
                    img = QImage(path)
                    if img.isNull():
                        raise SystemExit(f"cannot load {path}")
                    images[path] = img
    win_w = max(img.width() for img in images.values())
    win_h = max(img.height() for img in images.values())
    masks, pixmaps = {}, {}

    def frame_for(ch, pose, mirrored):
        key = (ch.locate(pose.image), mirrored)
        if key not in pixmaps:
            img = images[key[0]]
            if mirrored:
                img = img.mirrored(True, False)
            pixmaps[key] = QPixmap.fromImage(img)
            masks[key] = QRegion(QBitmap.fromImage(img.createAlphaMask()))
        return pixmaps[key], masks[key]

    class Sprite(QWidget):
        def __init__(self):
            flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                     | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
            if QGuiApplication.platformName() == "xcb":
                # override-redirect: Hyprland must not tile, border or animate
                # these tiny moving windows. This affects sprites only, not a
                # global "python" window rule that could break unrelated apps.
                flags |= Qt.X11BypassWindowManagerHint
            super().__init__(None, flags)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setFixedSize(win_w, win_h)
            self.pix = None

        def show_frame(self, pix, mask):
            self.pix = pix
            self.setMask(mask)              # once per frame change, not per paint
            self.update()

        def paintEvent(self, _event):
            if self.pix is None:
                return
            painter = QPainter(self)
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.transparent)  # no trails from the last pose
            painter.drawPixmap(0, 0, self.pix)

    mascots, sprites = [], []
    master = random.Random(args.seed)
    coordinator = ActionCoordinator()
    for ch in chars:
        def frame_w(pose, _ch=ch):
            return images[_ch.locate(pose.image)].width()
        rng = random.Random(master.getrandbits(64))
        m = Mascot(ch, rng, master.uniform(0, screen_w), screen_w, frame_w,
                   coordinator)
        mascots.append(m)
        sprites.append(Sprite())

    def place(m, sprite):
        ax, ay = m.anchor_on_window()
        sprite.move(int(screen_left + m.x - ax), int(floor_y - ay))

    def draw(m, sprite):
        pix, mask = frame_for(m.ch, m.pose, m.look_right)
        sprite.show_frame(pix, mask)

    for m, s in zip(mascots, sprites):
        draw(m, s)
        place(m, s)
        s.show()

    clock = QElapsedTimer()
    clock.start()
    last_ms = clock.elapsed()

    def tick():
        nonlocal last_ms
        now = clock.elapsed()
        # Clamp a debugger/suspend gap: catching up thousands of actions in one
        # paint event is not useful and would make every sprite teleport.
        elapsed = min(100.0, max(1.0, float(now - last_ms)))
        last_ms = now
        for m, s in zip(mascots, sprites):
            m.dirty = False
            m.advance(elapsed / TICK_MS)
            if m.dirty:
                draw(m, s)
            place(m, s)

    timer = QTimer()
    timer.setTimerType(Qt.PreciseTimer)
    timer.timeout.connect(tick)
    timer.start(round(RENDER_MS))

    if args.run_for:                       # test hook: stop after N seconds
        def finish():
            if args.snapshot:
                os.makedirs(args.snapshot, exist_ok=True)
                for m, s in zip(mascots, sprites):
                    s.grab().save(os.path.join(args.snapshot, f"{m.name}.png"))
            app.quit()
        QTimer.singleShot(int(args.run_for * 1000), finish)
    return app.exec()


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pack", default=DEFAULT_PACK, help="folder holding the four image sets")
    p.add_argument("--chars", default=",".join(CHARS), help="comma-separated character names")
    p.add_argument("--floor-margin", type=int, default=48,
                   help="px above the bottom edge where the characters stand (bar height)")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--simulate", type=int, metavar="TICKS",
                   help="schedule this many ticks without opening a window")
    p.add_argument("--screen-w", type=int, default=1920, help="width used by --simulate")
    p.add_argument("--run-for", type=float, metavar="SECONDS",
                   help=argparse.SUPPRESS)           # test hook: quit after N seconds
    p.add_argument("--snapshot", metavar="DIR", help=argparse.SUPPRESS)  # test hook
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    chars = [pack.load_character(args.pack, name) for name in args.chars.split(",")]
    if args.simulate:
        return simulate(args, chars)
    return run_desktop(args, chars)


if __name__ == "__main__":
    sys.exit(main())
