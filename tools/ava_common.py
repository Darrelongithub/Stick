#!/usr/bin/env python3
"""Single source of truth for the AvA Shimeji pack.

Everything the three tools must agree on lives here:

  * which characters exist
  * the canonical canvas + ImageAnchor of every action's frames
  * which action is rendered from which ``stickgen`` frame list
  * how each action is wired into conf/actions.xml (type/border/poses)
  * which behaviours exist, how often they fire per character, and where
    they are allowed to fire

``stickgen.py`` renders the frames, ``patch_xml.py`` writes the XML,
``validate.py`` checks the two agree.  Before this module existed the frame
counts lived twice (generator + XML) and drifted silently.

Canvas note
-----------
Every generated frame is 160x160 with 16px of slack on each side.  Poses are
still authored in the original 128x128 space (centre x=64, floor y=128); the
renderer pads them by +16,+16, so the anchor of a "floor" frame is 80,144.

That slack is what makes "the sprite is never clipped" structural: the art of
a generated frame can never touch the canvas edge, so Shimeji-ee can never
draw a limb cut in half and the window can never be smaller than the art.
The original pack's frames are left untouched at 128x128 / 64,128.
"""
import re

CHARS = ["Blue", "Orange", "Yellow", "Green"]

# ---------------------------------------------------------------- geometry
POSE_CANVAS = 128          # the coordinate space poses are authored in
PAD = 16                   # slack added on each side when rendering
CANVAS = POSE_CANVAS + 2 * PAD          # 160x160 generated frames

# ImageAnchor (in the rendered canvas) per action family.  Pose-space
# anchors are (64,128) floor / (64,0) ceiling / (0,128) wall; padding shifts
# them all by PAD.
FAMILY_ANCHOR = {
    "floor":   f"{64 + PAD},{128 + PAD}",   # 80,144
    "air":     f"{64 + PAD},{128 + PAD}",   # 80,144  (feet line while falling)
    "ceiling": f"{64 + PAD},{0 + PAD}",     # 80,16
    "wall":    f"{0 + PAD},{128 + PAD}",    # 16,144
}

# ---------------------------------------------------------------- actions
# Each entry:
#   prefix    frame file prefix (frames are <prefix>01.png, <prefix>02.png, ...)
#   frames    number of frames the generator must produce
#   family    which anchor the frames use (see FAMILY_ANCHOR)
#   type      Shimeji-ee action type
#   border    BorderType (or None)
#   loop      Loop attribute (or None -> emit nothing)
#   durations per-pose durations in 40ms Shimeji ticks; ints or Shimeji-ee
#             expressions, e.g. "${6+Math.random()*4}"
#   velocity  optional per-pose "vx,vy" (Move actions)
#   embed     optional dict of extra attributes (Embedded actions)
#   plays     pose order, as 1-based indexes into frames (defaults to 1..n)
#   compat    also emit as this XML action name (shared art, e.g. GrabWall)
#
# ``regen`` marks actions whose frames the generator renders (everything
# else is original pack art that the generator must not touch).
ACTIONS = {}


def _add(name, **kw):
    ACTIONS[name] = kw
    return kw


# ---- existing generated batch -------------------------------------------------
_add("Wave", prefix="wave", frames=4, family="floor", type="Animate", border="Floor",
     durations=[6, 4, 3, 3, 3, 3, 5], plays=[1, 2, 3, 4, 3, 4, 1], regen=True)
_add("Cheer", prefix="cheer", frames=6, family="floor", type="Animate", border="Floor",
     durations=[4, 3, 3, 3, 3, 6], regen=True)
_add("FightCombo", prefix="fight_stance", frames=6, family="floor", type="Animate", border="Floor",
     anim=("fight_stance", "fight_punch", "fight_kick", "fight_block"),
     files=["fight_stance01.png", "fight_stance02.png", "fight_punch01.png",
            "fight_punch02.png", "fight_kick01.png", "fight_block01.png"],
     durations=[4, 4, 2, 2, 3, 4, 4, 4],
     plays=[1, 2, 3, 4, 1, 5, 6, 2], regen=True)
_add("SwordPractice", prefix="sword", frames=5, family="floor", type="Animate", border="Floor",
     durations=[5, 3, 2, 2, 2, 2, 6], plays=[1, 2, 3, 4, 3, 4, 5], regen=True)
_add("Mine", prefix="mine", frames=4, family="floor", type="Animate", border="Floor",
     durations=[4, 2, 4, 3, 3, 2, 6], plays=[1, 2, 3, 4, 1, 2, 3], regen=True)
# Animate, not Stay: a "Stay" action loops until something else ends it, so a
# behaviour built on one would leave the character asleep (or stuck in a pose)
# forever.  The playback list breathes through the three sleep frames twice.
_add("Sleep", prefix="sleep", frames=3, family="floor", type="Animate", border="Floor",
     durations=[12, 10, 14, 14, 10, 12], plays=[1, 2, 3, 3, 2, 1], regen=True)
_add("Hurt", prefix="hurt", frames=3, family="floor", type="Animate", border="Floor",
     durations=[6, 6, 5, 10], plays=[1, 2, 1, 3], regen=True)
_add("CursorSlash", prefix="cursorslash", frames=3, family="floor", type="Animate", border="Floor",
     durations=[3, 3, 2, 5], plays=[1, 2, 2, 3], regen=True)
_add("GlitchOut", prefix="glitch", frames=3, family="floor", type="Animate", border="Floor",
     durations=[2, 2, 2, 2, 4], plays=[1, 2, 3, 1, 3], regen=True)
_add("Backflip", prefix="flip", frames=6, family="floor", type="Animate", border="Floor",
     durations=[3, 2, 2, 2, 2, 5], regen=True)
_add("SnackTime", prefix="snack", frames=4, family="floor", type="Animate", border="Floor",
     durations=[5, 4, 5, 4, 5], plays=[1, 2, 3, 3, 4], regen=True)
_add("PowerSlide", prefix="slide", frames=4, family="floor", type="Animate", border="Floor",
     durations=[3, 3, 4, 5], regen=True)
_add("PushUps", prefix="pushup", frames=4, family="floor", type="Animate", border="Floor",
     durations=[4, 4, 4, 4, 5], plays=[1, 2, 3, 4, 1], regen=True)
_add("Sneeze", prefix="sneeze", frames=3, family="floor", type="Animate", border="Floor",
     durations=[6, 4, 3, 5], plays=[1, 2, 2, 3], regen=True)
_add("PaperPlane", prefix="plane", frames=4, family="floor", type="Animate", border="Floor",
     durations=[5, 3, 5, 5], regen=True)

# ---- signatures --------------------------------------------------------------
_add("DrawAlive", prefix="draw", frames=6, family="floor", type="Animate", border="Floor",
     durations=[4, 4, 4, 4, 5, 8], regen=True, sig="Orange")
_add("Tinker", prefix="tinker", frames=4, family="floor", type="Animate", border="Floor",
     durations=[4, 4, 3, 3, 6], plays=[1, 2, 3, 2, 4], regen=True, sig="Yellow")
_add("BrewPotion", prefix="potion", frames=4, family="floor", type="Animate", border="Floor",
     durations=[5, 4, 4, 7], regen=True, sig="Blue")
_add("PlayGuitar", prefix="music", frames=4, family="floor", type="Animate", border="Floor",
     durations=[5, 4, 5, 4, 6], plays=[1, 2, 3, 4, 1], regen=True, sig="Green")

# ---- re-drawn pack actions ---------------------------------------------------
# These replace original art that was clipped, sunk below its anchor, or drawn
# on a canvas of the wrong size (Yellow fall01-03 were 161px wide with the arm
# sliced off; Green hang01-05 hung 211px below the ceiling; Orange's wall_climb
# legs sank up to 19px under the anchor; Blue's lay01 was cut on both sides).
# Falling and edge-crawling are cyclic, high-motion actions. They run at the
# host's full 25 fps instead of holding three near-static drawings for 1.6
# seconds each (the old Falling cadence). ``phase`` starts each colour at a
# different quarter of the 48-frame cycle, so four mascots spawned on the same
# host tick do not move like synchronized clones.
_add("Falling", prefix="fall", frames=48, family="air", type="Embedded", border=None,
     embed={"Class": "com.group_finity.mascot.action.Fall",
            "RegistanceX": "0.05", "RegistanceY": "0.1", "Gravity": "1"},
     durations=[1] * 48, phase={"Blue": 0, "Orange": 12, "Yellow": 24, "Green": 36},
     regen=True)
_add("GrabCeiling", prefix="hang", frames=16, family="ceiling", type="Stay", border="Ceiling",
     durations=[2] * 16,
     phase={"Blue": 0, "Orange": 4, "Yellow": 8, "Green": 12}, regen=True)
_add("ClimbCeiling", prefix="swing", frames=48, family="ceiling", type="Move", border="Ceiling",
     durations=[1] * 48, velocity=["-1,0"] * 48,
     phase={"Blue": 0, "Orange": 12, "Yellow": 24, "Green": 36}, regen=True)
_add("GrabWall", prefix="wall_hold", anim="wall_hold", frames=16, family="wall", type="Stay",
     border="Wall", durations=[2] * 16,
     phase={"Blue": 0, "Orange": 4, "Yellow": 8, "Green": 12}, regen=True)
_add("ClimbWall", prefix="wall_climb", frames=48, family="wall", type="Move", border="Wall",
     durations=[1] * 48, velocity=["0,-1"] * 48,
     phase={"Blue": 0, "Orange": 12, "Yellow": 24, "Green": 36},
     regen=True, two_animations=True)
_add("Sprawl", prefix="lay", frames=3, family="floor", type="Stay", border="Floor",
     durations=[40, 12, 60], regen=True)
_add("Tripping", prefix="trip", frames=6, family="floor", type="Animate", border="Floor",
     durations=[2, 2, 2, 4, 4, 16],
     velocity=[("-10,0"), ("-6,0"), ("-4,0"), ("-2,0"), ("0,0"), ("0,0")], regen=True)

# ---- new batch ---------------------------------------------------------------
_add("Stretch", prefix="stretch", frames=6, family="floor", type="Animate", border="Floor",
     durations=[6, 4, 6, 6, 4, 8], regen=True)
_add("Taunt", prefix="taunt", frames=6, family="floor", type="Animate", border="Floor",
     durations=[4, 3, 3, 3, 4, 6], regen=True)
_add("SpinKick", prefix="spin", frames=6, family="floor", type="Animate", border="Floor",
     durations=[3, 3, 2, 2, 2, 6], regen=True)
_add("Phone", prefix="phone", frames=6, family="floor", type="Animate", border="Floor",
     durations=[5, 4, 3, 4, 4, 6], regen=True)
_add("Coffee", prefix="coffee", frames=6, family="floor", type="Animate", border="Floor",
     durations=[5, 4, 4, 5, 4, 7], regen=True)
_add("Meditate", prefix="meditate", frames=6, family="floor", type="Animate", border="Floor",
     durations=[10, 10, 12, 12, 14, 12], regen=True)
_add("Cry", prefix="cry", frames=6, family="floor", type="Animate", border="Floor",
     durations=[5, 4, 4, 4, 4, 8], regen=True)
_add("Dizzy", prefix="dizzy", frames=5, family="floor", type="Animate", border="Floor",
     durations=[3, 3, 3, 4, 10], regen=True)
_add("Juggle", prefix="juggle", frames=7, family="floor", type="Animate", border="Floor",
     durations=[3, 3, 3, 3, 3, 3, 6], regen=True)
_add("Victory", prefix="victory", frames=7, family="floor", type="Animate", border="Floor",
     durations=[4, 3, 3, 3, 3, 5, 8], regen=True)
_add("Idle", prefix="idle", frames=8, family="floor", type="Animate", border="Floor",
     durations=[3] * 8,
     phase={"Blue": 0, "Orange": 2, "Yellow": 4, "Green": 6}, regen=True)

# A real low-to-the-floor crawl (separate from wall/ceiling crawling).  It is a
# finite moving Animate action so it can be selected directly as a behaviour;
# unlike a target-driven Move it never waits forever for an absent TargetX.
_add("Crawl", prefix="crawl", frames=48, family="floor", type="Animate", border="Floor",
     durations=[1] * 48, velocity=["-1,0"] * 48,
     phase={"Blue": 0, "Orange": 12, "Yellow": 24, "Green": 36}, regen=True)

# One additional move unique to each character.  Exclusive moves make the
# crew read as four personalities even when their host gives every mascot the
# same random seed.
_add("Cartwheel", prefix="cartwheel", frames=48, family="floor", type="Animate",
     border="Floor", durations=[1] * 48, regen=True, sig="Orange")
_add("ReadBook", prefix="read", frames=8, family="floor", type="Animate",
     border="Floor", durations=[5, 4, 4, 3, 4, 4, 5, 5],
     regen=True, sig="Blue")
_add("Inspect", prefix="inspect", frames=8, family="floor", type="Animate",
     border="Floor", durations=[4, 3, 3, 4, 3, 3, 4, 5],
     regen=True, sig="Yellow")
_add("JumpRope", prefix="jumprope", frames=24, family="floor", type="Animate",
     border="Floor", durations=[1] * 24, regen=True, sig="Green")

# ---- sequences (no frames of their own) --------------------------------------
SEQUENCES = {
    "BattleRage": ["FightCombo", "SwordPractice", "CursorSlash"],
    "Bonk": ["Hurt", "Stand"],
}

# ---------------------------------------------------------------- behaviours
# ``gate`` limits where a behaviour may be picked:
#   floor -> only while standing on the floor (or on top of a window)
#   None  -> anywhere (used by reactive/leaping moves)
FLOOR_GATE = ("#{mascot.environment.floor.isOn(mascot.anchor) || "
              "mascot.environment.activeIE.topBorder.isOn(mascot.anchor)}")
# Dance is deliberately stricter than the general floor activity gate: a
# window top is not a safe substitute for the actual desktop floor.
FLOOR_ONLY_GATE = "#{mascot.environment.floor.isOn(mascot.anchor)}"
CURSOR_NEAR = ("${Math.abs(mascot.anchor.x - mascot.environment.cursor.x) < 300 "
               "&& Math.abs(mascot.anchor.y - mascot.environment.cursor.y) < 300}")

# ShimeLinux 1.4.0's Shimeji-ee-compatible script context exposes the current
# `mascot`/`action`, environment, Math helpers, and population counts. Its
# manager does not expose a stable peer identity or shared animation state, so
# do not invent a cross-mascot condition; desynchronize with independent pools,
# weights, and tempo profiles instead.
# name -> (base frequency, gate, condition)
BEHAVIORS = [
    ("Idle",         18, "floor", None),        # animated breathing / weight shift
    ("Crawl",        14, "floor_only", None),   # active floor locomotion
    ("Dance",        10, "floor_only", None),   # only on the real work-area floor
    ("Wave",         20, "floor", None),
    ("Cheer",        14, "floor", None),
    ("Stretch",      12, "floor", None),
    ("FightCombo",   16, "floor", None),
    ("SwordPractice", 12, "floor", None),
    ("BattleRage",    7, None,    None),
    ("SpinKick",      8, "floor", None),
    ("Taunt",        10, "floor", None),
    ("CursorSlash",  16, None,    CURSOR_NEAR),
    ("Mine",         10, "floor", None),
    ("Juggle",        7, "floor", None),
    ("Phone",        10, "floor", None),
    ("Coffee",       10, "floor", None),
    ("Meditate",      8, "floor", None),
    ("Sleep",        14, "floor", None),
    ("PushUps",       7, "floor", None),
    ("SnackTime",    10, "floor", None),
    ("PaperPlane",    8, "floor", None),
    ("Sneeze",        6, "floor", None),
    ("Backflip",     10, "floor", None),
    ("PowerSlide",    8, None,    None),
    ("GlitchOut",     6, None,    None),
    ("Dizzy",         6, "floor", None),
    ("Cry",           5, "floor", None),
    ("Victory",       9, "floor", None),
    ("Hurt",          8, "floor", None),
    ("Bonk",          6, None,    None),
]

# What each character reaches for more (or less) often - the four are
# supposed to feel like different people, not one animation reel.
FLAVOR = {
    "Orange": {"FightCombo": 1.6, "SpinKick": 1.4, "DrawAlive": 1.4, "Victory": 1.3,
               "Wave": 0.8, "Meditate": 0.6, "Coffee": 0.8, "Tinker": 0.0,
               "Dance": 1.4, "Crawl": 0.7, "Idle": 0.55, "Stretch": 0.8,
               "Cheer": 1.3},
    "Blue":   {"BrewPotion": 1.4, "Meditate": 1.6, "Sleep": 1.4, "Coffee": 1.3,
               "FightCombo": 0.7, "Dizzy": 0.7, "Tinker": 0.0, "Idle": 0.8,
               "Crawl": 0.6, "Dance": 0.3, "Wave": 1.2, "Stretch": 1.3,
               "Cheer": 0.8},
    "Yellow": {"Tinker": 1.5, "Juggle": 1.5, "Mine": 1.3, "Phone": 1.3,
               "Cry": 0.6, "Sleep": 0.8, "Taunt": 1.2, "Crawl": 1.5,
               "Dance": 0.6, "Idle": 0.65, "Wave": 1.4, "Stretch": 0.8,
               "Cheer": 1.1},
    "Green":  {"PlayGuitar": 1.5, "Cheer": 1.3, "Coffee": 1.3, "PushUps": 1.3,
               "Phone": 0.7, "Sleep": 0.9, "Stretch": 1.2, "Crawl": 1.1,
               "Dance": 1.6, "Idle": 0.7, "Wave": 0.8, "Taunt": 1.1},
}

# Per-frame accent patterns (added to existing Dance durations) make the same
# sprite choreography breathe at four distinctly recognizable tempos.
DANCE_TEMPO_ACCENTS = {
    "Blue":   (0, 0, 1, 0, 0, 1, 0, 0),  # gentle, measured sway
    "Orange": (1, 0, 0, 0, 0, 0, 1, 0),  # punchy accents
    "Yellow": (0, 1, 0, 0, 1, 0, 0, 0),  # playful skip
    "Green":  (0, 0, 0, 1, 0, 0, 0, 1),  # relaxed long beats
}
# Keep the original mapping public for compatibility with existing pack tools,
# and layer the new exclusive move on top through ``signature_behaviors``.
SIG_BEHAVIORS = {"Orange": ("DrawAlive", 18), "Yellow": ("Tinker", 18),
                 "Blue": ("BrewPotion", 18), "Green": ("PlayGuitar", 18)}
EXTRA_SIG_BEHAVIORS = {
    "Orange": [("Cartwheel", 17)],
    "Blue": [("ReadBook", 16)],
    "Yellow": [("Inspect", 17)],
    "Green": [("JumpRope", 17)],
}


def signature_behaviors(char):
    """Ordered ``(action, frequency)`` pairs exclusive to ``char``."""
    return [SIG_BEHAVIORS[char], *EXTRA_SIG_BEHAVIORS.get(char, ())]

# Behaviours from the original pack that this pack switches off.  Breeding is
# the big one: PullUpShimeji let every character clone itself while walking
# (capped only at 50 mascots), which is what buried the desktop in shimejis.
# These behaviours and their cloning actions/references are removed, not just
# given zero weight (libshijima can still select zero-weight behaviours).
# ``Breeding=false`` in settings.properties backs this up at the app level.
DISABLED_BEHAVIORS = ["PullUpShimeji"]


def freq(action, char):
    """Frequency of `action`'s behaviour for `char` (0 = never fires)."""
    base = next((f for n, f, _g, _c in BEHAVIORS if n == action), None)
    if base is None:
        base = next((f for n, f in signature_behaviors(char) if n == action), None)
    if base is None:
        return 0
    scale = FLAVOR.get(char, {}).get(action, 1.0)
    return int(round(base * scale))


def gate(action):
    for n, _f, g, _c in BEHAVIORS:
        if n == action:
            if g == "floor_only":
                return FLOOR_ONLY_GATE
            return FLOOR_GATE if g == "floor" else None
    return None


def condition(action):
    for n, _f, _g, c in BEHAVIORS:
        if n == action:
            return c
    return None


def anchor(action):
    """ImageAnchor written into conf/actions.xml for `action`'s poses."""
    return FAMILY_ANCHOR[ACTIONS[action]["family"]]


def generated_actions():
    """Actions whose frames stickgen renders, in a stable order."""
    return [n for n, a in ACTIONS.items() if a.get("regen")]


def generated_actions_for(char):
    """`generated_actions` minus the signature moves belonging to others - a
    signature is one character's own move, so it is only drawn for them."""
    return [n for n in generated_actions()
            if ACTIONS[n].get("sig") in (None, char)]


def sig_for(char):
    return [n for n, a in ACTIONS.items() if a.get("sig") == char]


def frame_names(action):
    a = ACTIONS[action]
    if a.get("files"):
        return list(a["files"])
    return [f"{a['prefix']}{i + 1:02d}.png" for i in range(a["frames"])]


def poses(action, char=None):
    """[(image, anchor, velocity, duration), ...] in playback order.

    ``durations``/``velocity`` either describe the frame files one-to-one, or
    - when ``plays`` repeats frames - the playback list.  That is why the
    lengths are compared before zipping.  Cyclic actions can declare a stable
    per-character phase; this is applied to velocity and duration together so
    the choreography remains internally consistent.
    """
    a = ACTIONS[action]
    names = frame_names(action)
    durations = a["durations"]
    vel = a.get("velocity") or ["0,0"] * len(names)
    if len(durations) == len(names) and len(vel) == len(names):
        pairs = list(zip(names, vel, durations))
    else:
        plays = a.get("plays") or list(range(1, len(names) + 1))
        pairs = []
        for i, idx in enumerate(plays):
            pairs.append((names[idx - 1],
                          vel[i] if i < len(vel) else "0,0",
                          durations[i] if i < len(durations) else 4))
    if char and pairs:
        if len(pairs) == 1 and char in (a.get("start_frame") or {}):
            _img, velocity, duration = pairs[0]
            pairs[0] = (names[int(a["start_frame"][char]) - 1], velocity, duration)
        phase = int((a.get("phase") or {}).get(char, 0)) % len(pairs)
        pairs = pairs[phase:] + pairs[:phase]
    return [(img, anchor(action), v, d) for img, v, d in pairs]


# Slightly different long-beat placement prevents two independently hosted
# mascots from staying locked together after choosing the same one-shot move.
# Fast one-tick locomotion is left untouched; phase offsets handle those loops.
TEMPO_PROFILES = {
    "Blue": (5, 0),
    "Orange": (11, 3),
    "Yellow": (7, 2),
    "Green": (3, 1),
}


def duration_for(action, char, index, duration):
    """Return a stable, subtle personality timing accent for one pose."""
    if not isinstance(duration, int) or duration < 3:
        return duration
    period, offset = TEMPO_PROFILES[char]
    salt = sum(ord(c) for c in action)
    return duration + (1 if (index + salt) % period == offset else 0)


def expected_images():
    """{char: sorted list of frame files the generator must produce}."""
    return {c: sorted({f for n in generated_actions_for(c) for f in frame_names(n)})
            for c in CHARS}


def self_check():
    """Raise if the spec contradicts itself (called by the tools)."""
    problems = []
    for name, a in ACTIONS.items():
        n_files = a["frames"]
        n_dur = len(a["durations"])
        n_vel = len(a.get("velocity") or [])
        n_plays = len(a.get("plays") or [])
        if "plays" in a:
            if n_plays != n_dur:
                problems.append(f"{name}: {n_plays} plays but {n_dur} durations")
            if n_vel and n_vel != n_plays:
                problems.append(f"{name}: {n_vel} velocities but {n_plays} plays")
            if any(not 1 <= p <= n_files for p in a["plays"]):
                problems.append(f"{name}: plays references a missing frame")
        elif n_dur != n_files:
            problems.append(f"{name}: {n_files} frames but {n_dur} durations")
        elif n_vel and n_vel != n_files:
            problems.append(f"{name}: {n_vel} velocities but {n_files} frames")
        if a.get("files") and len(a["files"]) != n_files:
            problems.append(f"{name}: {len(a['files'])} files but frames={n_files}")
        if a["family"] not in FAMILY_ANCHOR:
            problems.append(f"{name}: unknown family {a['family']!r}")
        if a["type"] == "Embedded" and not a.get("embed"):
            problems.append(f"{name}: Embedded action without attributes")
    for name in SEQUENCES:
        if name in ACTIONS:
            problems.append(f"{name}: is both a sequence and a frame action")
    for char in CHARS:
        signature_names = {n for n, _f in signature_behaviors(char)}
        for sig in sig_for(char):
            if BEHAVIORS and not any(n == sig for n, _f, _g, _c in BEHAVIORS) \
                    and sig not in signature_names:
                problems.append(f"{char}: signature {sig} has no behaviour")
    if problems:
        raise AssertionError("ava_common spec is inconsistent:\n  " + "\n  ".join(problems))


SLUG_RE = re.compile(r"[^a-z0-9]+")
