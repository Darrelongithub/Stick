#!/usr/bin/env python3
"""Append new AvA actions + behaviors to each character's Shimeji-ee XML.

Per-name idempotent: only inserts actions/behaviors not already present.
Preserves UTF-8 BOM and CRLF line endings exactly. Validates XML after
patching.

Shimeji-ee rules this script must respect:

* Each actions.xml has TWO <ActionList> sections; generated actions are
  inserted before the FIRST </ActionList> ONLY (str.replace with count=1).
  Inserting before every close duplicated every action and Shimeji-ee
  aborted with "duplicate action found: wave".
* A Behavior resolves its action by the Behavior's OWN Name - an
  <ActionReference> child is not valid inside <Behavior>. So generated
  behaviors are emitted as <Behavior Name="<action name>" ... /> with the
  action's name, no child elements.
* "Is this already present?" must be asked per ELEMENT. A bare
  `Name="Wave" in raw` substring test is also satisfied by
  <ActionReference Name="Wave"/> inside a Sequence action, which silently
  suppressed inserting the real <Action Name="Wave"> - Shimeji-ee then
  failed to load with "no corresponding action Wave".
"""
import os, re, sys, xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARS = ["Blue", "Orange", "Yellow", "Green"]

# An XML start tag (self-closing or not). Comments, PIs and CDATA never match:
# they do not begin with a name character. Well-formed XML cannot contain a
# raw ">" inside an attribute value (it must be &gt;), so [^>]* stays in-tag.
START_TAG_RE = re.compile(r'<([A-Za-z_][\w:.-]*)\b([^>]*?)/?>', re.S)


def attr_value(attrs, name):
    """Value of attribute `name` inside a tag's attribute text, in any
    position, double- or single-quoted. None when absent."""
    m = re.search(r'(?:^|\s)' + re.escape(name) + r'\s*=\s*'
                  r'("([^"]*)"|\'([^\']*)\')', attrs)
    if not m:
        return None
    return m.group(2) if m.group(2) is not None else m.group(3)


def element_present(raw, tag, name):
    """True iff `<tag ... Name="name" ...>` exists as an ELEMENT in `raw`.
    Attribute order is irrelevant; a differently named element (e.g.
    <ActionReference Name="Wave"/>) never counts as <Action Name="Wave">."""
    return any(m.group(1) == tag and attr_value(m.group(2), "Name") == name
               for m in START_TAG_RE.finditer(raw))

def element_start_re(tag, name):
    """Compiled matcher for a `<tag ... Name="name"` opening, any attribute
    order - used to locate an insertion anchor."""
    return re.compile(r'<' + re.escape(tag) + r'\b[^>]*?\bName="'
                      + re.escape(name) + r'"')

def pose(img, dur, vx=0, vy=0, anchor="64,128"):
    return (f'\t\t\t\t<Pose Image="/{img}" ImageAnchor="{anchor}" '
            f'Velocity="{vx},{vy}" Duration="{dur}" />')

def action(name, type_, border, poses):
    lines = [f'\t\t<Action Name="{name}" Type="{type_}" BorderType="{border}">',
             '\t\t\t<Animation>'] + [pose(*p) for p in poses] + \
            ['\t\t\t</Animation>', '\t\t</Action>', '']
    return (name, lines)

def seq_action(name, refs):
    lines = [f'\t\t<Action Name="{name}" Type="Sequence" Loop="false">']
    for r in refs:
        lines.append(f'\t\t\t<ActionReference Name="{r}" />')
    return (name, lines + ['\t\t</Action>', ''])

def behavior(action_name, freq, cond=None):
    # The Behavior's Name IS the action it runs (Shimeji-ee looks the action
    # up by the Behavior's own Name; no ActionReference child allowed).
    c = f' Condition="{cond}"' if cond else ''
    return (action_name, [f'\t\t<Behavior Name="{action_name}" Frequency="{freq}"{c} />'])

CURSOR_NEAR = ("${Math.abs(mascot.anchor.x - mascot.environment.cursor.x) &lt; 300 "
               "&amp;&amp; Math.abs(mascot.anchor.y - mascot.environment.cursor.y) &lt; 300}")

# ---------------- actions ----------------
# CRISP TIMING: key poses 2-3 ticks, transitions 3-4, holds 4-5
COMMON_ACTIONS = [
    action("Wave", "Animate", "Floor", [
        ("wave01.png", 5), ("wave02.png", 3), ("wave03.png", 2), ("wave04.png", 3),
        ("wave03.png", 2), ("wave04.png", 3), ("wave01.png", 4)]),
    action("Cheer", "Animate", "Floor", [
        ("cheer01.png", 3), ("cheer02.png", 2), ("cheer03.png", 3),
        ("cheer04.png", 3), ("cheer05.png", 3), ("cheer06.png", 4)]),
    action("SwordPractice", "Animate", "Floor", [
        ("sword01.png", 4), ("sword02.png", 2), ("sword03.png", 2),
        ("sword04.png", 2), ("sword03.png", 2), ("sword04.png", 2), ("sword05.png", 4)]),
    action("Mine", "Animate", "Floor", [
        ("mine01.png", 3), ("mine02.png", 2), ("mine03.png", 3), ("mine04.png", 3),
        ("mine01.png", 3), ("mine02.png", 2), ("mine03.png", 4)]),
    action("Sleep", "Stay", "Floor", [
        ("sleep01.png", 10), ("sleep02.png", 10), ("sleep03.png", 25)]),
    action("Hurt", "Animate", "Floor", [
        ("hurt01.png", 4), ("hurt02.png", 4), ("hurt01.png", 3), ("hurt03.png", 8)]),
    action("CursorSlash", "Animate", "Floor", [
        ("cursorslash01.png", 3), ("cursorslash02.png", 2), ("cursorslash02.png", 2),
        ("cursorslash03.png", 4)]),
    action("GlitchOut", "Animate", "Floor", [
        ("glitch01.png", 2), ("glitch02.png", 2), ("glitch03.png", 2),
        ("glitch01.png", 2), ("glitch03.png", 3)]),
    seq_action("Bonk", ["Hurt", "Stand"]),
    # --- movement & show-off ---
    action("Backflip", "Animate", "Floor", [
        ("flip01.png", 2), ("flip02.png", 2), ("flip03.png", 2),
        ("flip04.png", 2), ("flip05.png", 2), ("flip06.png", 3)]),
    action("SnackTime", "Animate", "Floor", [
        ("snack01.png", 4), ("snack02.png", 3), ("snack03.png", 4),
        ("snack03.png", 3), ("snack04.png", 4)]),
    action("PowerSlide", "Animate", "Floor", [
        ("slide01.png", 2), ("slide02.png", 3), ("slide03.png", 3), ("slide04.png", 4)]),
    action("PushUps", "Animate", "Floor", [
        ("pushup01.png", 3), ("pushup02.png", 3), ("pushup01.png", 3),
        ("pushup02.png", 3), ("pushup01.png", 4)]),
    action("Sneeze", "Animate", "Floor", [
        ("sneeze01.png", 4), ("sneeze02.png", 3), ("sneeze02.png", 2), ("sneeze03.png", 4)]),
    action("PaperPlane", "Animate", "Floor", [
        ("plane01.png", 4), ("plane02.png", 3), ("plane03.png", 4), ("plane04.png", 4)]),
    # --- diverse actions ---
    action("Yawn", "Animate", "Floor", [
        ("yawn01.png", 4), ("yawn02.png", 6), ("yawn03.png", 4), ("yawn04.png", 4)]),
    action("HeadScratch", "Animate", "Floor", [
        ("headscratch01.png", 3), ("headscratch02.png", 3),
        ("headscratch03.png", 4), ("headscratch04.png", 3)]),
    action("FistPump", "Animate", "Floor", [
        ("fistpump01.png", 3), ("fistpump02.png", 2),
        ("fistpump03.png", 3), ("fistpump04.png", 3)]),
    action("Think", "Animate", "Floor", [
        ("think01.png", 4), ("think02.png", 4), ("think03.png", 5), ("think04.png", 4)]),
    action("Faint", "Animate", "Floor", [
        ("faint01.png", 3), ("faint02.png", 3), ("faint03.png", 2),
        ("faint04.png", 3), ("faint05.png", 10)]),
    action("Sneak", "Animate", "Floor", [
        ("sneak01.png", 4), ("sneak02.png", 4), ("sneak03.png", 3), ("sneak04.png", 4)]),
    action("Shrug", "Animate", "Floor", [
        ("shrug01.png", 3), ("shrug02.png", 3), ("shrug03.png", 4), ("shrug04.png", 3)]),
    action("Jump", "Animate", "Floor", [
        ("jump01.png", 2), ("jump02.png", 2), ("jump03.png", 2),
        ("jump04.png", 3), ("jump05.png", 3)]),
    action("Facepalm", "Animate", "Floor", [
        ("facepalm01.png", 3), ("facepalm02.png", 3),
        ("facepalm03.png", 6), ("facepalm04.png", 5)]),
    action("Dab", "Animate", "Floor", [
        ("dab01.png", 2), ("dab02.png", 3), ("dab03.png", 4), ("dab04.png", 3)]),
    action("Balance", "Animate", "Floor", [
        ("balance01.png", 4), ("balance02.png", 4), ("balance03.png", 4),
        ("balance04.png", 4), ("balance05.png", 4)]),
    action("PanicSpin", "Animate", "Floor", [
        ("panicspin01.png", 2), ("panicspin02.png", 2), ("panicspin03.png", 2),
        ("panicspin04.png", 2), ("panicspin05.png", 3), ("panicspin06.png", 3)]),
    action("Celebrate", "Animate", "Floor", [
        ("celebrate01.png", 3), ("celebrate02.png", 2), ("celebrate03.png", 3),
        ("celebrate04.png", 3), ("celebrate05.png", 4)]),
    action("WallJump", "Animate", "Floor", [
        ("walljump01.png", 3), ("walljump02.png", 3), ("walljump03.png", 2),
        ("walljump04.png", 3), ("walljump05.png", 3)]),
    action("Hover", "Animate", "Floor", [
        ("hover01.png", 3), ("hover02.png", 4), ("hover03.png", 3), ("hover04.png", 3)]),
    action("SprintDash", "Animate", "Floor", [
        ("dash01.png", 2), ("dash02.png", 2), ("dash03.png", 2),
        ("dash04.png", 2), ("dash05.png", 2), ("dash06.png", 2)]),
]

SIG_ACTIONS = {
    "Orange": [action("DrawAlive", "Animate", "Floor", [
        ("draw01.png", 3), ("draw02.png", 3), ("draw03.png", 3),
        ("draw04.png", 3), ("draw05.png", 4), ("draw06.png", 5)])],
    "Yellow": [action("Tinker", "Animate", "Floor", [
        ("tinker01.png", 3), ("tinker02.png", 3), ("tinker03.png", 3),
        ("tinker02.png", 3), ("tinker04.png", 4)])],
    "Blue": [action("BrewPotion", "Animate", "Floor", [
        ("potion01.png", 4), ("potion02.png", 3), ("potion03.png", 3), ("potion04.png", 5)])],
    "Green": [action("PlayGuitar", "Stay", "Floor", [
        ("music01.png", 3), ("music02.png", 3), ("music03.png", 3), ("music04.png", 3)])],
}

# Behavior names are the action names (see behavior()); Shimeji-ee resolves
# a Behavior's action by the Behavior's own Name.
COMMON_BEHAVIORS = [
    behavior("Wave", 80),
    behavior("Cheer", 70),
    behavior("SwordPractice", 75),
    behavior("Mine", 70),
    behavior("Sleep", 40),
    behavior("CursorSlash", 80, CURSOR_NEAR),
    behavior("GlitchOut", 50),
    behavior("Bonk", 40),
    behavior("Backflip", 75),
    behavior("SnackTime", 70),
    behavior("PowerSlide", 70),
    behavior("PushUps", 60),
    behavior("Sneeze", 55),
    behavior("PaperPlane", 65),
    behavior("Yawn", 65),
    behavior("HeadScratch", 60),
    behavior("FistPump", 65),
    behavior("Think", 65),
    behavior("Faint", 45),
    behavior("Sneak", 60),
    behavior("Shrug", 60),
    behavior("Jump", 75),
    behavior("Facepalm", 55),
    behavior("Dab", 50),
    behavior("Balance", 60),
    behavior("PanicSpin", 40),
    behavior("Celebrate", 55),
    behavior("WallJump", 65),
    behavior("Hover", 65),
    behavior("SprintDash", 50),
]

SIG_BEHAVIORS = {
    "Orange": [behavior("DrawAlive", 75)],
    "Yellow": [behavior("Tinker", 75)],
    "Blue": [behavior("BrewPotion", 75)],
    "Green": [behavior("PlayGuitar", 75)],
}

def patch_actions(path, wanted):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    # Element-scoped test: only a real <Action Name="X"> counts as present.
    missing = [(n, l) for n, l in wanted
               if not element_present(raw, "Action", n)]
    if not missing:
        print(f"  {path}: actions up to date")
        return
    block = eol.join(['\t\t<!-- AvA custom animations (Stick pack generator) -->'] +
                     [ln for _, l in missing for ln in l])
    if "</ActionList>" not in raw:
        raise SystemExit(f"REFUSING to patch {path}: no </ActionList> to insert into")
    # Insert into the FIRST </ActionList> only: each actions.xml has two
    # <ActionList> sections and Shimeji-ee rejects duplicate action names
    # ("duplicate action found: ...").
    raw = raw.replace("</ActionList>", block + eol + "\t</ActionList>", 1)
    with open(path, "wb") as f:
        f.write(raw.encode("utf-8"))
    print(f"  {path}: +{len(missing)} actions {[n for n, _ in missing]}")

def behavior_element_end(raw, start):
    """Index just past the Behavior element that opens at raw[start]:
    end of its line if self-closing, else just past its </Behavior>."""
    nl = raw.find("\n", start)
    if nl == -1:
        return len(raw)
    if raw[start:nl].rstrip().endswith("/>"):
        return nl + 1
    close = raw.find("</Behavior>", start)
    if close == -1:
        raise SystemExit(f"unterminated <Behavior> at offset {start}")
    return close + len("</Behavior>")


def last_element_start(raw, tag, name):
    """Offset of the last `<tag ... Name="name"` opening in raw, any
    attribute order, or -1 when there is none."""
    pos = -1
    for m in element_start_re(tag, name).finditer(raw):
        pos = m.start()
    return pos


def patch_behaviors(path, wanted):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    # Element-scoped test: a <BehaviorReference Name="X"/> child of some other
    # behavior does not mean behavior X already exists.
    missing = [(n, l) for n, l in wanted
               if not element_present(raw, "Behavior", n)]
    if not missing:
        print(f"  {path}: behaviors up to date")
        return
    block = eol.join(['\t\t<!-- AvA custom behaviors (Stick pack generator) -->'] +
                     [ln for _, l in missing for ln in l])
    # insert after the last already-present wanted behavior if any, else
    # after the stock Dance behavior, else before </BehaviorList>
    anchor = -1
    for n, _ in wanted:
        i = last_element_start(raw, "Behavior", n)
        if i > anchor:
            anchor = i
    if anchor == -1:
        anchor = last_element_start(raw, "Behavior", "Dance")
    if anchor != -1:
        end = behavior_element_end(raw, anchor)
        raw = raw[:end] + eol + block + raw[end:]
    else:
        if "</BehaviorList>" not in raw:
            raise SystemExit(f"REFUSING to patch {path}: no </BehaviorList> to insert into")
        raw = raw.replace("</BehaviorList>", block + eol + "\t</BehaviorList>", 1)
    with open(path, "wb") as f:
        f.write(raw.encode("utf-8"))
    print(f"  {path}: +{len(missing)} behaviors {[n for n, _ in missing]}")

def disable_cloning(path):
    """Kill PullUpShimeji breeding behavior to prevent infinite cloning."""
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    orig = raw
    # PullUpShimeji is a Breed action that spawns new mascots - disable it
    raw = re.sub(
        r'(<Behavior\s+Name="PullUpShimeji"\s+[^>]*?)Frequency="[^"]*"',
        r'\1Frequency="0"',
        raw)
    # Also reduce PullUp behavior frequency
    raw = re.sub(
        r'(<Behavior\s+Name="PullUp"\s+[^>]*?)Frequency="[^"]*"',
        r'\1Frequency="0"',
        raw)
    # Reduce HugSearch from stock 1000 to 50 (was hogging 19% of behavior pool)
    raw = re.sub(
        r'(<Behavior\s+Name="HugSearch"\s+[^>]*?)Frequency="[^"]*"',
        r'\1Frequency="50"',
        raw)
    # Reduce stock movement behaviors from 100 to 60
    move_behaviors = [
        'WalkAlongWorkAreaFloor','RunAlongWorkAreaFloor',
        'WalkLeftAlongFloorAndSit','WalkRightAlongFloorAndSit',
        'GrabWorkAreaBottomLeftWall','GrabWorkAreaBottomRightWall',
        'WalkLeftAndSit','WalkRightAndSit',
        'RunAndGrabBottomLeftWall','RunAndGrabBottomRightWall',
        'ClimbHalfwayAlongWall','ClimbAlongWall','ClimbAlongCeiling',
        'WalkAlongIECeiling','RunAlongIECeiling',
        'SitOnTheLeftEdgeOfIE','SitOnTheRightEdgeOfIE',
        'JumpFromLeftEdgeOfIE','JumpFromRightEdgeOfIE',
        'WalkLeftAlongIEAndSit','WalkRightAlongIEAndSit',
        'WalkLeftAlongIEAndJump','WalkRightAlongIEAndJump',
        'HoldOntoIEWall','ClimbIEWall','ClimbIEBottom',
        'GrabIEBottomLeftWall','GrabIEBottomRightWall',
        'HoldOntoWall','HoldOntoCeiling',
    ]
    for beh in move_behaviors:
        raw = re.sub(
            r'(<Behavior\s+Name="' + re.escape(beh) + r'"\s+[^>]*?)Frequency="100"',
            r'\1Frequency="60"',
            raw)
    if raw != orig:
        with open(path, "wb") as f:
            f.write(raw.encode("utf-8"))
        print(f"  {path}: disabled breeding + rebalanced frequencies")

def main():
    prefixes = ("wave", "cheer", "sword", "mine", "sleep", "hurt",
                "cursorslash", "glitch", "draw", "tinker", "potion", "music",
                "flip", "snack", "slide", "pushup", "sneeze", "plane", "dash",
                "yawn", "headscratch", "fistpump", "think", "faint",
                "sneak", "shrug", "jump", "facepalm", "dab",
                "balance", "panicspin", "celebrate", "walljump", "hover")
    for char in CHARS:
        print(char)
        a_path = os.path.join(ROOT, "AVA Shimejis", char, "conf", "actions.xml")
        b_path = os.path.join(ROOT, "AVA Shimejis", char, "conf", "behaviors.xml")
        patch_actions(a_path, COMMON_ACTIONS + SIG_ACTIONS[char])
        patch_behaviors(b_path, COMMON_BEHAVIORS + SIG_BEHAVIORS[char])
        disable_cloning(b_path)
        tree = ET.parse(a_path)
        ET.parse(b_path)
        names = {p.get("Image").lstrip("/") for p in tree.getroot().iter()
                 if p.tag.endswith("Pose") and p.get("Image")}
        missing = [n for n in sorted(names) if n.startswith(prefixes)
                   and not os.path.exists(os.path.join(ROOT, "AVA Shimejis", char, n))]
        if missing:
            print(f"  MISSING IMAGES in {char}: {missing}")
            sys.exit(1)
        print(f"  {char}: XML valid, all new images present")

if __name__ == "__main__":
    main()