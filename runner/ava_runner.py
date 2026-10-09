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

TICK_MS = 40                     # Shimeji-ee's tick; one pose "Duration" unit
CHARS = ["Blue", "Orange", "Yellow", "Green"]
DEFAULT_PACK = os.path.join(ROOT, "AVA Shimejis")

# Floor actions that are not something a free-roaming buddy should start by
# itself (they are triggered by the environment in Shimeji-ee).
EXCLUDE = {"Falling", "Fall", "Dragged", "Thrown", "Pinched", "Resisting", "Offset"}
# Relative odds when a new action is picked.  Anything not listed weighs 1.
WEIGHTS = {"Idle": 3, "Walk": 4, "Run": 2, "Sleep": 2, "Sit": 2, "Meditate": 2}


def floor_actions(ch):
    """Actions a character may start on its own, standing on the floor."""
    pool = []
    for name, act in ch.actions.items():
        if not act.poses or name in EXCLUDE:
            continue
        if act.kind not in ("Animate", "Move", "Stay"):
            continue
        if (act.border or "Floor") != "Floor":
            continue
        pool.append(act)
    return pool


class Mascot:
    """Scheduling and position for one character.  No drawing in here."""

    def __init__(self, ch, rng, x, screen_w, frame_w=None):
        self.ch = ch
        self.name = ch.name
        self.rng = rng
        self.pool = floor_actions(ch)
        if not self.pool:
            raise ValueError(f"{ch.name}: no floor actions to play")
        self.weights = [WEIGHTS.get(a.name, 1) for a in self.pool]
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
        self.action = self.rng.choices(self.pool, self.weights)[0]
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

    def step(self):
        """Advance one tick.  Sets ``dirty`` when the displayed frame changes."""
        dx = self.pose.velocity[0] * (-1 if self.look_right else 1)
        if dx:
            new_x = min(max(self.x + dx, 0.0), float(self.screen_w))
            if new_x != self.x + dx:           # hit a screen edge: end the move
                self.left = 0
            self.x = new_x
        self.left -= 1
        if self.left > 0:
            return
        self.index += 1
        if self.index >= len(self.action.poses):
            self._start_next()
        else:
            self.pose = self.action.poses[self.index]
            self.left = self.pose.duration
            self.dirty = True

    # -- drawing helpers --------------------------------------------------
    def anchor_on_window(self):
        """Window top-left (x, y offset from the anchor) for the current frame."""
        ax, ay = self.pose.anchor
        if self.look_right:
            ax = self.frame_w(self.pose) - ax
        return ax, ay


def simulate(args, chars):
    rng = random.Random(args.seed)
    mascots = [Mascot(c, rng, rng.uniform(0, args.screen_w), args.screen_w)
               for c in chars]
    out_of_bounds = 0
    frame_changes = [0] * len(mascots)
    for _ in range(args.simulate):
        for i, m in enumerate(mascots):
            m.dirty = False
            m.step()
            if m.dirty:
                frame_changes[i] += 1
            if not (0 <= m.x <= args.screen_w):
                out_of_bounds += 1
    seconds = args.simulate * TICK_MS / 1000
    print(f"simulated {seconds:.0f}s of {len(mascots)} characters "
          f"({args.simulate} ticks x {TICK_MS} ms)")
    for m, changes in zip(mascots, frame_changes):
        top = ", ".join(f"{n} x{c}" for n, c in m.started.most_common(4))
        print(f"  {m.name:7s} {changes / seconds:5.1f} frame changes/s "
              f"| {sum(m.started.values())} actions | {top}")
    print(f"out-of-bounds positions: {out_of_bounds}")
    return 0 if out_of_bounds == 0 else 1


def run_desktop(args, chars):
    try:
        from PySide6.QtCore import QLockFile, Qt, QTimer
        from PySide6.QtGui import QBitmap, QGuiApplication, QImage, QPainter, QPixmap, QRegion
        from PySide6.QtWidgets import QApplication, QWidget
    except ImportError as exc:
        sys.stderr.write(f"ava-runner: the desktop part could not start: {exc}\n"
                         "  needs PySide6 plus the system OpenGL/xkb libraries:\n"
                         "    pip install PySide6-Essentials\n"
                         "    Debian/Ubuntu: libgl1 libegl1 libxkbcommon0 libfontconfig1\n"
                         "    Arch: mesa libxkbcommon fontconfig\n"
                         "  (--simulate needs none of this)\n")
        return 2

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # One runner at a time, however it was started (systemd, Hyprland, by hand).
    lock = QLockFile(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                                  "ava-runner.lock"))
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
            super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                             | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                             | Qt.NoDropShadowWindowHint)
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
            painter.drawPixmap(0, 0, self.pix)

    mascots, sprites = [], []
    rng = random.Random(args.seed)
    for ch in chars:
        def frame_w(pose, _ch=ch):
            return images[_ch.locate(pose.image)].width()
        m = Mascot(ch, rng, rng.uniform(0, screen_w), screen_w, frame_w)
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

    def tick():
        for m, s in zip(mascots, sprites):
            m.dirty = False
            m.step()
            if m.dirty:
                draw(m, s)
            place(m, s)

    timer = QTimer()
    timer.setTimerType(Qt.PreciseTimer)
    timer.timeout.connect(tick)
    timer.start(TICK_MS)

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
