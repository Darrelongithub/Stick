#!/usr/bin/env python3
"""Validate the AvA Shimeji pack's Shimeji-ee conf files.

Checks every character (Blue, Orange, Yellow, Green):

  * conf/actions.xml and conf/behaviors.xml are well-formed XML
  * no duplicate Action names (checked exactly and case-insensitively)
  * every Behavior's effective action (its Action attribute if present,
    else its Name) exists among the actions
  * every ActionReference (in actions.xml AND behaviors.xml) resolves to
    an existing action
  * every BehaviorReference resolves to an existing Behavior,
    and there are no duplicate Behavior names
  * every <Pose Image="/x.png"> file exists in that character's folder AND
    stays inside it: "..", NUL bytes and empty image paths are rejected
  * no files ending in ~ (editor backups) anywhere in the pack

Exits non-zero if anything fails. Run from anywhere; paths are resolved
relative to the repository root (parent of this script's directory).
"""
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARS = ["Blue", "Orange", "Yellow", "Green"]
REQUIRED_JARS_NOTE = "jna.jar examples.jar AbsoluteLayout.jar nimrodlf.jar"


def local(tag):
    """Strip any XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def check_char(char, failures):
    base = os.path.join(ROOT, "AVA Shimejis", char)
    a_path = os.path.join(base, "conf", "actions.xml")
    b_path = os.path.join(base, "conf", "behaviors.xml")

    # ---- well-formedness -------------------------------------------------
    try:
        a_root = ET.parse(a_path).getroot()
    except ET.ParseError as exc:
        failures.append(f"{char}: actions.xml is not well-formed XML: {exc}")
        return None
    try:
        b_root = ET.parse(b_path).getroot()
    except ET.ParseError as exc:
        failures.append(f"{char}: behaviors.xml is not well-formed XML: {exc}")
        return None

    # ---- action names ----------------------------------------------------
    actions = [e.get("Name") for e in a_root.iter()
               if local(e.tag) == "Action" and e.get("Name")]
    action_set = set(actions)
    seen, seen_ci = set(), {}
    for name in actions:
        if name in seen:
            failures.append(f'{char}: duplicate action name "{name}" in actions.xml')
        seen.add(name)
        low = name.lower()
        if low in seen_ci and seen_ci[low] != name:
            failures.append(
                f'{char}: action names "{seen_ci[low]}" and "{name}" collide '
                f"case-insensitively in actions.xml")
        seen_ci.setdefault(low, name)

    # ---- behaviors -------------------------------------------------------
    behaviors = [e.get("Name") for e in b_root.iter()
                 if local(e.tag) == "Behavior" and e.get("Name")]
    behavior_set = set(behaviors)
    b_seen, b_seen_ci = set(), {}
    for name in behaviors:
        if name in b_seen:
            failures.append(f'{char}: duplicate behavior name "{name}" in behaviors.xml')
        b_seen.add(name)
        low = name.lower()
        if low in b_seen_ci and b_seen_ci[low] != name:
            failures.append(
                f'{char}: behavior names "{b_seen_ci[low]}" and "{name}" collide '
                f"case-insensitively in behaviors.xml")
        b_seen_ci.setdefault(low, name)

    # ---- every Behavior's effective action exists -------------------------
    for e in b_root.iter():
        if local(e.tag) != "Behavior":
            continue
        effective = e.get("Action") or e.get("Name")
        if effective not in action_set:
            failures.append(
                f'{char}: behavior "{e.get("Name")}" resolves to action '
                f'"{effective}" which does not exist')

    # ---- ActionReference targets (both files) -----------------------------
    for root, fname in ((a_root, "actions.xml"), (b_root, "behaviors.xml")):
        for e in root.iter():
            if local(e.tag) == "ActionReference" and e.get("Name"):
                if e.get("Name") not in action_set:
                    failures.append(
                        f'{char}: {fname} ActionReference "{e.get("Name")}" '
                        f"points at a non-existent action")

    # ---- BehaviorReference targets ----------------------------------------
    for e in b_root.iter():
        if local(e.tag) == "BehaviorReference" and e.get("Name"):
            if e.get("Name") not in behavior_set:
                failures.append(
                    f'{char}: behaviors.xml BehaviorReference "{e.get("Name")}" '
                    f"points at a non-existent behavior")

    # ---- pose images -------------------------------------------------------
    # A pose path is resolved relative to the character folder. Anything that
    # climbs out of it (../, a NUL, an empty value) must be rejected outright:
    # a <Pose Image="/../secret.png"> would otherwise happily load a frame
    # from outside the image set.
    for e in a_root.iter():
        if local(e.tag) != "Pose":
            continue
        raw_img = e.get("Image")
        if raw_img is None or raw_img.strip() == "":
            failures.append(f"{char}: {a_path}: <Pose> has no usable Image= value")
            continue
        if "\x00" in raw_img:
            failures.append(
                f'{char}: {a_path}: pose image "{raw_img!r}" contains a NUL '
                f"byte - not a usable path")
            continue
        img = raw_img.replace("\\", "/").lstrip("/")
        if any(part == ".." for part in img.split("/")):
            failures.append(
                f'{char}: {a_path}: pose image "{raw_img}" escapes the '
                f"character folder ({base}) - frames must live inside it")
            continue
        target = os.path.join(base, img)
        if not os.path.isfile(target):
            failures.append(
                f'{char}: {a_path}: pose image "{raw_img}" '
                f"not found in {base}")
            continue
        # last line of defence: a symlink inside the set could still point out
        real = os.path.realpath(target)
        if os.path.commonpath([os.path.realpath(base), real]) \
                != os.path.realpath(base):
            failures.append(
                f'{char}: {a_path}: pose image "{raw_img}" resolves outside '
                f"the character folder ({base})")

    # ---- no editor backup files --------------------------------------------
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if fn.endswith("~"):
                failures.append(
                    f"{char}: stray backup file: "
                    f"{os.path.relpath(os.path.join(dirpath, fn), ROOT)}")

    return len(actions), len(behaviors)


def check_repo(failures):
    """Repo-wide sanity: no editor backups outside .git and the pack folders
    (the per-character check already covers those)."""
    skip = {".git", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if os.path.abspath(dirpath) == ROOT:
            dirnames[:] = [d for d in dirnames if d != "AVA Shimejis"]
        for fn in filenames:
            if fn.endswith("~"):
                failures.append(
                    "stray backup file: "
                    f"{os.path.relpath(os.path.join(dirpath, fn), ROOT)}")


def main():
    failures = []
    print(f"Validating AvA Shimeji pack in {ROOT}")
    for char in CHARS:
        counts = check_char(char, failures)
        if counts is None:
            print(f"  {char}: FAIL (unparseable XML)")
        elif not any(f.startswith(f"{char}:") for f in failures):
            print(f"  {char}: OK "
                  f"({counts[0]} actions, {counts[1]} behaviors)")
        else:
            print(f"  {char}: FAIL")
    check_repo(failures)

    if failures:
        print(f"\n{len(failures)} problem(s) found:")
        for f in failures:
            print(f"  - {f}")
        print("\nVALIDATION FAILED")
        return 1
    print("\nAll checks passed for Blue, Orange, Yellow, Green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
