#!/usr/bin/env python3
"""Validate the AvA Shimeji pack.

Everything is checked against tools/ava_common.py, so the generator, the XML
and this file can never disagree about how many frames an action has, where
its anchor sits, or which behaviours exist.

Structural checks (exit non-zero on failure - because Shimeji-ee either
refuses to load the pack or renders it wrong):

  * both conf XMLs parse, no duplicate action/behaviour names (Shimeji-ee
    aborts on duplicates: "duplicate action found"), every reference resolves
  * PullUpShimeji is disabled (breeding off -> the crew stays at four)
  * the stock Dance behaviour has no unresolvable <ActionReference>
  * every generated frame file exists, is exactly the spec canvas size, and
    has no ink touching the canvas edge - a frame whose art reaches the edge
    is a frame whose art gets cut in half on screen
  * every <Pose> anchor equals the spec anchor for that action's family
  * the generator's frame lists match the spec frame counts
  * no files ending in ~ (editor backups) anywhere in the pack
  * every action type / embedded class the XML uses is one that libshijima
    (Shijima-Qt) implements - Shijima-Qt refuses to load a mascot whole if an
    action type is unknown, so linux/shijima.sh would silently produce
    unloadable .mascot folders otherwise

Advisory report (never fails): how often each character will do what, so a
"the animations feel repetitive" complaint can be answered with numbers.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ava_common as SPEC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Art is allowed to come this close to the canvas edge (px). 1 = "must not
# touch"; generated frames sit 16+ px clear by construction.
EDGE_TOLERANCE = 1


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def check_xml(char, failures):
    base = os.path.join(ROOT, "AVA Shimejis", char)
    a_path = os.path.join(base, "conf", "actions.xml")
    b_path = os.path.join(base, "conf", "behaviors.xml")
    try:
        a_root = ET.parse(a_path).getroot()
    except ET.ParseError as exc:
        failures.append(f"{char}: actions.xml is not well-formed XML: {exc}")
        return None, None
    try:
        b_root = ET.parse(b_path).getroot()
    except ET.ParseError as exc:
        failures.append(f"{char}: behaviors.xml is not well-formed XML: {exc}")
        return None, None

    actions = [e.get("Name") for e in a_root.iter()
               if local(e.tag) == "Action" and e.get("Name")]
    action_set = set(actions)
    for name, count in Counter(actions).items():
        if count > 1:
            failures.append(f'{char}: duplicate action name "{name}" in actions.xml')
    for name, count in Counter(n.lower() for n in actions).items():
        if count > 1:
            failures.append(f"{char}: action names collide case-insensitively: {name}")

    behaviors = [e.get("Name") for e in b_root.iter()
                 if local(e.tag) == "Behavior" and e.get("Name")]
    behavior_set = set(behaviors)
    for name, count in Counter(behaviors).items():
        if count > 1:
            failures.append(f'{char}: duplicate behavior name "{name}" in behaviors.xml')

    # every behaviour needs an action of the same name (the behaviour's own
    # Name is what Shimeji-ee resolves - an ActionReference child is not valid)
    for b in b_root.iter():
        if local(b.tag) != "Behavior":
            continue
        name = b.get("Name")
        if not name:
            continue
        if list(b) and any(local(c.tag).startswith("ActionReference") for c in b):
            failures.append(f'{char}: <Behavior Name="{name}"> has an '
                            f"<ActionReference> child - Shimeji-ee resolves the "
                            f"action by the behaviour's Name, not its children")
        if name not in action_set:
            failures.append(f'{char}: behavior "{name}" has no matching action')
        if int(b.get("Frequency") or 0) > 0 and name in SPEC.DISABLED_BEHAVIORS:
            failures.append(f'{char}: behavior "{name}" is enabled again '
                            f'(breeding clones the crew - it must stay off)')

    for ref in a_root.iter():
        if local(ref.tag) == "ActionReference":
            n = ref.get("Name")
            if n and n not in action_set:
                failures.append(f'{char}: <ActionReference Name="{n}"/> in '
                                f"actions.xml resolves to nothing")
    for ref in b_root.iter():
        if local(ref.tag) == "BehaviorReference":
            n = ref.get("Name")
            if n and n not in behavior_set:
                failures.append(f'{char}: <BehaviorReference Name="{n}"/> in '
                                f"behaviors.xml resolves to nothing")
    return a_root, b_root


def check_frames(char, a_root, failures, report, advisories):
    """Generated frames must not touch any edge.  For the pack's original art
    (which this repo keeps as-is) a horizontal slice is only reported when it
    is actually wrong: art is *meant* to sit on the bottom edge when the feet
    are on the floor line, and against the left/top edge when the character is
    wall- or ceiling-anchored."""
    from PIL import Image

    base = os.path.join(ROOT, "AVA Shimejis", char)
    expected = set()
    if a_root is None:
        return
    for node in a_root.iter():
        if local(node.tag) != "Action":
            continue
        action = node.get("Name")
        for pose in node.iter():
            if local(pose.tag) != "Pose":
                continue
            img = (pose.get("Image") or "").lstrip("/")
            anchor = pose.get("ImageAnchor") or "?"
            expected.add(img)
            path = os.path.join(base, img)
            if not img or not os.path.exists(path):
                failures.append(f"{char}: pose image {img!r} is missing")
                continue
            with Image.open(path) as im:
                size = im.size
                box = im.convert("RGBA").getbbox()
            if box is None:
                failures.append(f"{char}/{img}: frame is completely transparent")
                continue
            generated = any(img.startswith(p) for p in generated_prefixes())
            l, t, r, b = box
            edges = []
            if l < EDGE_TOLERANCE:
                edges.append("left")
            if t < EDGE_TOLERANCE:
                edges.append("top")
            if r > size[0] - EDGE_TOLERANCE:
                edges.append("right")
            if b > size[1] - EDGE_TOLERANCE:
                edges.append("bottom")
            if generated:
                if size != (SPEC.CANVAS, SPEC.CANVAS):
                    failures.append(f"{char}/{img}: is {size[0]}x{size[1]}, "
                                    f"expected {SPEC.CANVAS}x{SPEC.CANVAS}")
                if edges:
                    failures.append(
                        f"{char}/{img}: generated frame's art {box} touches the "
                        f"{'/'.join(edges)} edge - that limb is cut in half")
                continue
            # ---- original art: only report the slices that are really wrong
            try:
                ax, ay = (int(v) for v in anchor.split(","))
            except ValueError:
                ax, ay = -1, -1
            bad = []
            if ("left" in edges or "right" in edges) and ax == 64:
                bad.append("side")
            if "top" in edges and ay > 0:
                bad.append("top")
            if bad:
                advisories[(action, img, "/".join(bad))] += 1
    for action in SPEC.generated_actions_for(char):
        want_anchor = SPEC.anchor(action)
        want_files = SPEC.frame_names(action)
        for f in want_files:
            if not os.path.exists(os.path.join(base, f)):
                failures.append(f"{char}: {action} is missing frame {f}")
        node = next((x for x in a_root.iter()
                     if local(x.tag) == "Action" and x.get("Name") == action), None)
        if node is None:
            failures.append(f'{char}: actions.xml has no <Action Name="{action}">')
            continue
        poses = [p for p in node.iter() if local(p.tag) == "Pose"]
        if not poses:
            failures.append(f"{char}: {action} has no poses")
        for p in poses:
            if p.get("ImageAnchor") != want_anchor:
                failures.append(f'{char}: {action} pose {p.get("Image")} anchor '
                                f'{p.get("ImageAnchor")} != spec {want_anchor}')
            img = (p.get("Image") or "").lstrip("/")
            if img not in want_files:
                failures.append(f"{char}: {action} uses {img}, which the spec "
                                f"does not list for it")
    report[char] = len(expected)


def generated_prefixes():
    prefixes = set()
    for a in SPEC.ACTIONS.values():
        prefixes.add(a["prefix"])
    return prefixes


def check_stale(char, failures):
    """Managed frame files that the spec no longer produces."""
    base = os.path.join(ROOT, "AVA Shimejis", char)
    if not os.path.isdir(base):
        failures.append(f"{char}: image folder is missing")
        return
    want = {f for a in SPEC.generated_actions_for(char) for f in SPEC.frame_names(a)}
    for name in sorted(os.listdir(base)):
        if not name.endswith(".png"):
            continue
        for p in sorted(generated_prefixes(), key=len, reverse=True):
            if name.startswith(p):
                if name not in want:
                    failures.append(f"{char}/{name}: stale generated frame "
                                    f"(re-run tools/stickgen.py --prune)")
                break


def check_generator(failures):
    """The generator's frame lists must match the spec."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import stickgen
    except Exception as exc:                                  # pragma: no cover
        failures.append(f"cannot import tools/stickgen.py: {exc}")
        return
    for action in SPEC.generated_actions():
        want = SPEC.ACTIONS[action]["frames"]
        got = len(stickgen.anim_frames(action))
        if got != want:
            failures.append(f"stickgen: {action} has {got} poses, spec wants {want}")


# Action types libshijima implements (Shijima-Qt's parser).  Types not in this
# set make Shijima-Qt fail to load the mascot, so they must never appear.
SHIJIMA_TYPES = {
    # instant
    "Offset", "Look", "Mute",
    # animation-like
    "Jump", "Animate", "Broadcast", "Breed", "BreedJump", "BreedMove",
    "Dragged", "Regist", "Stay", "BroadcastStay", "Move", "Turn",
    "MoveWithTurn", "BroadcastMove", "BroadcastJump", "Fall", "ScanMove",
    "Interact", "SelfDestruct", "Transform", "ScanInteract", "ScanJump",
    "ComplexMove", "ComplexJump", "FallWithIE", "WalkWithIE", "ThrowIE",
    # structural
    "Sequence", "Select",
}
SHIJIMA_CLASS_PREFIX = "com.group_finity.mascot.action."


def check_shijima(char, a_root, failures):
    """Shijima-Qt must be able to parse this actions.xml too."""
    for node in a_root.iter():
        tag = local(node.tag)
        if tag != "Action" and tag != "ActionReference":
            continue
        kind = node.get("Type")
        if kind and kind not in SHIJIMA_TYPES:
            if kind == "Embedded":
                cls = (node.get("Class") or "")
                if not cls.startswith(SHIJIMA_CLASS_PREFIX):
                    failures.append(f"{char}: Embedded action {node.get('Name')!r} has "
                                    f"class {cls!r} - libshijima rejects that")
                elif cls[len(SHIJIMA_CLASS_PREFIX):] not in SHIJIMA_TYPES:
                    failures.append(f"{char}: action {node.get('Name')!r} uses class "
                                    f"{cls!r}, which Shijima-Qt does not implement")
            else:
                failures.append(f"{char}: action {node.get('Name')!r} has type {kind!r}, "
                                f"which Shijima-Qt does not implement")


def behaviour_report(ok, out=sys.stdout):
    """How often each character does what - the anti-repetition overview."""
    print("\nBehaviours per character (frequency at each decision point)", file=out)
    names = [n for n, _f, _g, _c in SPEC.BEHAVIORS]
    names += [SPEC.SIG_BEHAVIORS[c][0] for c in SPEC.CHARS]
    width = max(len(n) for n in names)
    print("  " + " " * width + "  " + "".join(f"{c:>9s}" for c in SPEC.CHARS), file=out)
    for n in names:
        row = "".join(f"{SPEC.freq(n, c) or '-':>9}" for c in SPEC.CHARS)
        print(f"  {n:{width}s}  {row}", file=out)
    print("  " + "-" * (width + 2 + 9 * len(SPEC.CHARS)), file=out)
    totals = {c: sum(SPEC.freq(n, c) for n in names) for c in SPEC.CHARS}
    print(f"  {'TOTAL':{width}s}  " + "".join(f"{totals[c]:>9d}" for c in SPEC.CHARS),
          file=out)
    for c in SPEC.CHARS:
        # how much of the character's own repertoire is unique to them
        others = set()
        for o in SPEC.CHARS:
            if o != c:
                others |= {n for n in names if SPEC.freq(n, o)}
        mine = {n for n in names if SPEC.freq(n, c)}
        print(f"  {c:7s}: {len(mine):2d}/"
              f"{len([n for n in mine if n not in others])} moves are theirs alone",
              file=out)


def main():
    failures = []
    report = {}
    advisories = Counter()
    SPEC.self_check()
    check_generator(failures)
    for char in SPEC.CHARS:
        a_root, b_root = check_xml(char, failures)
        if a_root is not None:
            check_shijima(char, a_root, failures)
        check_frames(char, a_root, failures, report, advisories)
        check_stale(char, failures)
    for dirpath, _dirnames, filenames in os.walk(os.path.join(ROOT, "AVA Shimejis")):
        for name in filenames:
            if name.endswith("~"):
                failures.append(f"{os.path.join(dirpath, name)}: editor backup file")
    if advisories:
        print("Advisory - original pack art that is tight against its canvas.")
        print("(The frames this repo generates are all inside their margins; "
              "these are the original PNGs it keeps unchanged.)")
        grouped = defaultdict(Counter)
        for (action, img, edge), count in advisories.items():
            grouped[f"{action} ({edge})"][img] += count
        for key in sorted(grouped):
            imgs = sorted(grouped[key])
            print(f"  {key:22s} {len(imgs):3d} frame(s): "
                  f"{', '.join(imgs[:4])}{' ...' if len(imgs) > 4 else ''}")
        print()
    if failures:
        print(f"{len(failures)} problem(s):")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    total = sum(report.values())
    print(f"OK - {len(SPEC.CHARS)} characters, {total} pose references, "
          f"{len(SPEC.generated_actions())} generated actions, "
          f"{len(SPEC.SEQUENCES)} sequences (Shimeji-ee and Shijima-Qt)")
    behaviour_report(report)


if __name__ == "__main__":
    main()
