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
sys.path.insert(0, os.path.join(ROOT, "tools"))
import pack  # noqa: E402
from coordinator import ActionCoordinator  # noqa: E402

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
    if action is None:
        return ()                       # stationary waiting idle owns no turn
    names = tuple(os.path.basename(name) for name in action.images)
    # Cyclic XML is quarter-phase shifted per character. Canonicalize rotations
    # so Crawl still reserves one shared visual even when Blue starts at 01 and
    # Orange starts at 05.
    return min(names[i:] + names[:i] for i in range(len(names)))


def choose_action(pool, weights, rng, recent):
    """Personality affects selection, never the right to animate concurrently."""
    recent = set(recent)
    choices = [(a, w) for a, w in zip(pool, weights) if visual_key(a) not in recent]
    choices = choices or list(zip(pool, weights))
    if not choices:
        raise ValueError("empty animation pool")
    return rng.choices([a for a, _ in choices], [w for _, w in choices])[0]


def pump_schedule(coordinator, mascots):
    """Grant at most one lease, after all owners have advanced this update."""
    lease = coordinator.pump()
    if lease is not None:
        next(m for m in mascots if m.name == lease.request.owner).begin(lease)
    return lease


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
        self.coordinator = coordinator or ActionCoordinator([ch.name])
        self.coordinator.register(ch.name)
        self.recent = collections.deque(maxlen=4)
        self.screen_w = screen_w
        self.x = float(x)
        self.look_right = False
        self.idle_pose = (ch.actions.get("Stand") or ch.actions.get("Idle")
                          or self.pool[0]).poses[0]
        self.action = None
        self.lease = None
        self.index = 0
        self.left = 0
        self.elapsed = 0.0
        self.pose = self.idle_pose
        self.dirty = True
        self.frame_w = frame_w or (lambda _pose: 160)
        self.started = collections.Counter()
        self.finished = collections.Counter()
        self.blocked = False
        self._request_next()
        pump_schedule(self.coordinator, [self])

    def _request_next(self):
        action = choose_action(self.pool, self.weights, self.rng, self.recent)
        return self.coordinator.request(self.name, action)

    def request(self, action=None):
        """Public request API: append, never interrupt or start immediately."""
        if action is not None and action not in self.pool:
            raise ValueError(f"{self.name}: action is not playable: {action}")
        return self.coordinator.request(self.name, action)

    def begin(self, lease):
        if self.lease is not None or lease.request.owner != self.name:
            raise RuntimeError("cannot overlap an owner's playback")
        action = lease.request.payload
        if action is None or not action.poses:
            raise ValueError("a lease must contain a finite pose list")
        self.lease, self.action = lease, action
        self.index, self.elapsed, self.blocked = 0, 0.0, False
        self.pose = action.poses[0]
        self.left = self.pose.duration
        self.started[action.name] += 1
        if any(p.velocity[0] for p in action.poses):
            if self.x < self.screen_w * 0.2:
                self.look_right = True
            elif self.x > self.screen_w * 0.8:
                self.look_right = False
            else:
                self.look_right = self.rng.random() < 0.5
        self.dirty = True

    def _finish(self):
        # Freeze FIRST. Only then acknowledge the final pose's actual expiry.
        action, lease = self.action, self.lease
        self.recent.append(visual_key(action))
        self.finished[action.name] += 1
        self.action, self.lease = None, None
        self.pose, self.index, self.left = self.idle_pose, 0, 0
        self.dirty = True
        self.coordinator.complete(self.name, lease.token,
                                  frame_count=len(action.poses),
                                  elapsed_ticks=self.elapsed)
        self._request_next()

    def advance(self, ticks):
        """Consume exact pose durations; inactive figures cannot move or tick."""
        ticks = max(0.0, float(ticks))
        if self.lease is None:
            return
        while ticks > 1e-9 and self.lease is not None:
            chunk = min(ticks, float(self.left))
            dx = self.pose.velocity[0] * (-1 if self.look_right else 1) * chunk
            if dx and not self.blocked:
                target = self.x + dx
                self.x = min(max(target, 0.0), float(self.screen_w))
                # A wall stops translation, not the performance. Never skip the
                # remaining poses just to give another character the stage.
                self.blocked = abs(self.x - target) > 1e-9
            self.left -= chunk
            self.elapsed += chunk
            ticks -= chunk
            if self.left > 1e-9:
                continue
            self.index += 1
            if self.index >= len(self.action.poses):
                self._finish()
            else:
                self.pose = self.action.poses[self.index]
                self.left = self.pose.duration
                self.dirty = True

    def step(self):
        self.advance(1.0)
        pump_schedule(self.coordinator, [self])

    # -- drawing helpers --------------------------------------------------
    def anchor_on_window(self):
        """Window top-left (x, y offset from the anchor) for the current frame."""
        ax, ay = self.pose.anchor
        if self.look_right:
            ax = self.frame_w(self.pose) - ax
        return ax, ay


def simulate(args, chars):
    master = random.Random(args.seed)
    coordinator = ActionCoordinator([ch.name for ch in chars])
    mascots = [Mascot(c, random.Random(master.getrandbits(64)),
                      master.uniform(0, args.screen_w), args.screen_w,
                      coordinator=coordinator) for c in chars]
    violations = inactive_changes = 0
    changes = [0] * len(mascots)
    for _ in range(args.simulate):
        coordinator.tick += 1
        before = [(m.x, m.pose, m.index, m.lease) for m in mascots]
        for m in mascots:
            m.dirty = False
            m.advance(1.0)
        pump_schedule(coordinator, mascots)
        active = [m for m in mascots if m.lease is not None]
        violations += max(0, len(active) - 1)
        for i, m in enumerate(mascots):
            changes[i] += bool(m.dirty)
            # Only a mascot that was already inactive before this tick counts.
            # The completing owner may legitimately move during its final tick.
            if before[i][3] is None and m.lease is None and m.x != before[i][0]:
                inactive_changes += 1
    seconds = args.simulate * TICK_MS / 1000
    print(f"simulated {seconds:.0f}s of {len(mascots)} characters")
    for m, count in zip(mascots, changes):
        print(f"  {m.name:7s} {sum(m.started.values()):4d} granted | "
              f"{sum(m.finished.values()):4d} completed | {count:5d} frame changes")
    print(f"simultaneous active animations: {violations}")
    print(f"inactive character translation: {inactive_changes}")
    print(f"queued requests: {len(coordinator.queue)}")
    return 0 if violations == inactive_changes == 0 else 1


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
    # Construction only queues; grant the first turn after the crew exists.
    pump_schedule(coordinator, mascots)

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
        coordinator.tick += max(1, int(round(elapsed / TICK_MS)))
        for m in mascots:
            m.dirty = False
            m.advance(elapsed / TICK_MS)
        pump_schedule(coordinator, mascots)
        for m, s in zip(mascots, sprites):
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
