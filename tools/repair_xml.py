#!/usr/bin/env python3
"""Repair conf XMLs damaged by the old, buggy tools/patch_xml.py.

The old script had two bugs that made Shimeji-ee refuse to load the pack:

1. DUPLICATE ACTIONS ("duplicate action found: wave")
   It inserted its block before EVERY </ActionList> (str.replace replaces
   all occurrences), and each actions.xml has TWO <ActionList> sections, so
   every generated action ended up defined twice.

2. BROKEN BEHAVIORS ("no corresponding action Backflipper")
   It emitted <Behavior Name="Backflipper" ...><ActionReference Name=
   "Backflip" /></Behavior>, but Shimeji-ee resolves a Behavior's action by
   the Behavior's own Name; an <ActionReference> child is not valid inside
   <Behavior>, so "Backflipper" had to exist as an action - it didn't.

This script repairs both in place, for every character:

* actions.xml: keep the FIRST definition of each action name, delete later
  duplicates together with the blank line that followed them. The action name
  is matched in ANY attribute position, so <Action Type="Animate"
  Name="Wave"> duplicates are repaired just like <Action Name="Wave" ...>.
  Marker comments the old script left orphaned at the tail of a section (a
  comment with no action between it and the next marker/</ActionList>) are
  dropped, restoring the stock layout.
* behaviors.xml: any Behavior whose Name has no same-named action and that
  has exactly one <ActionReference> child whose target action exists gets
  its Name set to that target and the child dropped (the element becomes a
  self-closing <Behavior ... /> if nothing else remains). Behaviors that
  already have a same-named action (e.g. Dance) are left untouched.

Formatting is preserved byte-for-byte apart from the repairs: UTF-8 BOM and
CRLF/LF line endings are kept exactly as they are (including a missing
final newline). Each file is parsed and must be well-formed before and
after editing; a file is only rewritten when something actually changed.
The repair is idempotent: running it a second time changes nothing.

Usage: python3 tools/repair_xml.py [character ...]   (default: all four)
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARS = ["Blue", "Orange", "Yellow", "Green"]
BOM = b"\xef\xbb\xbf"
MARKER = "AvA custom animations (Stick pack generator)"
# Name= may sit in ANY attribute position: the old, narrower
# r'<Action\s+Name="..."' only saw it as the first attribute, so duplicates
# written as <Action Type="Animate" Name="Wave"> survived the repair and
# Shimeji-ee still aborted with "duplicate action found: wave".
# \b keeps <ActionList>/<ActionReference> out; [^>]*? keeps the match in-tag.
ACTION_START = re.compile(r'<Action\b[^>]*?\bName="([^"]+)"', re.S)


def behavior_open_re(name):
    """Matcher for a `<Behavior ... Name="name"` opening, any attribute
    order."""
    return re.compile(r'<Behavior\b[^>]*?\bName="' + re.escape(name) + r'"')


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def read_text(path):
    """Read a conf file, returning (text, had_bom, eol). BOM is stripped
    from the text so it can be parsed/re-added cleanly."""
    with open(path, "rb") as f:
        data = f.read()
    bom = data.startswith(BOM)
    text = data.decode("utf-8-sig" if bom else "utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    return text, bom, eol


def write_text(path, text, bom):
    with open(path, "wb") as f:
        f.write((BOM if bom else b"") + text.encode("utf-8"))


def parse_must_work(text, path):
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise SystemExit(f"REFUSING to touch {path}: not well-formed XML ({exc})")


def split_lines(text, eol):
    """Split into (line-contents, trailing-chunk). The trailing chunk is the
    text after the last eol ('' when the file ends with a newline)."""
    parts = text.split(eol)
    return parts[:-1], parts[-1]


def join_lines(lines, trailing, eol):
    if not lines:
        return trailing
    return eol.join(lines) + eol + trailing


def action_element_end(lines, start):
    """Index of the line on which the <Action> opened at lines[start] ends."""
    if lines[start].rstrip().endswith("/>"):
        return start
    i = start
    while i < len(lines) and "</Action>" not in lines[i]:
        i += 1
    if i >= len(lines):
        raise SystemExit(f"unterminated <Action> near line {start + 1}")
    return i


def dedupe_actions(lines):
    """Keep the first definition of each action name; drop later duplicates
    plus the blank line that followed them. Returns (lines, removed_names)."""
    seen, drop, removed = set(), set(), []
    i = 0
    while i < len(lines):
        m = ACTION_START.search(lines[i])
        if m:
            name = m.group(1)
            end = action_element_end(lines, i)
            if name in seen:
                removed.append(name)
                j = end + 1
                if j < len(lines) and lines[j].strip() == "":
                    j += 1  # also drop the following blank line
                drop.update(range(i, j))
            else:
                seen.add(name)
            i = end + 1
            continue
        i += 1
    return [l for k, l in enumerate(lines) if k not in drop], removed


def drop_orphan_markers(lines):
    """Remove marker comments the generator inserted that now have no action
    between them and the next marker comment or </ActionList>."""
    changed = True
    while changed:
        changed = False
        for i, line in enumerate(lines):
            if "<!--" not in line or MARKER not in line:
                continue
            for j in range(i + 1, len(lines)):
                if ACTION_START.search(lines[j]):
                    break  # actions follow: keep this marker
                if ("<!--" in lines[j] and MARKER in lines[j]) \
                        or "</ActionList>" in lines[j]:
                    del lines[i]  # orphaned: nothing was inserted after it
                    changed = True
                    break
            if changed:
                break
    return lines


def plan_behavior_renames(behaviors_root, action_names):
    """{old_name: new_name} for Behaviors with no same-named action whose
    single ActionReference child targets an existing action."""
    renames = {}
    for elem in behaviors_root.iter():
        if local(elem.tag) != "Behavior":
            continue
        name = elem.get("Name")
        if not name or name in action_names:
            continue
        refs = [c for c in elem if local(c.tag) == "ActionReference"]
        if len(refs) == 1 and refs[0].get("Name") \
                and refs[0].get("Name") in action_names:
            renames[name] = refs[0].get("Name")
    return renames


def apply_behavior_renames(lines, renames):
    """Rename Behavior opening tags and drop their ActionReference child.
    Elements left with no other children become self-closing."""
    for old, new in renames.items():
        # Name= may sit in any attribute position, same as for actions.
        opener = behavior_open_re(old)
        start = next((k for k, l in enumerate(lines) if opener.search(l)), None)
        if start is None:
            raise SystemExit(f'Behavior "{old}" not found for renaming')
        lines[start] = re.sub(r'\bName="' + re.escape(old) + r'"',
                              lambda _m, new=new: f'Name="{new}"',
                              lines[start], count=1)
        if lines[start].rstrip().endswith("/>"):
            continue  # self-closing already: no child to drop
        end = start
        while "</Behavior>" not in lines[end]:
            end += 1
        children = [k for k in range(start + 1, end)
                    if "<ActionReference" in lines[k]]
        others = [k for k in range(start + 1, end)
                  if k not in children and lines[k].strip() != ""]
        for k in children:
            lines[k] = None  # drop the invalid child
        if not others:
            # nothing left inside: make the opening tag self-closing
            lines[start] = lines[start].rstrip()[:-1].rstrip() + " />"
            lines[start + 1:end + 1] = []
        else:
            lines[start + 1:end + 1] = [l for l in lines[start + 1:end + 1]
                                        if l is not None]
    return lines


def repair_character(char):
    base = os.path.join(ROOT, "AVA Shimejis", char)
    a_path = os.path.join(base, "conf", "actions.xml")
    b_path = os.path.join(base, "conf", "behaviors.xml")
    report = []

    # ---------- actions.xml: dedupe duplicate action definitions ----------
    text, bom, eol = read_text(a_path)
    a_root = parse_must_work(text, a_path)
    action_names = [e.get("Name") for e in a_root.iter()
                    if local(e.tag) == "Action" and e.get("Name")]
    lines, trailing = split_lines(text, eol)
    lines, removed = dedupe_actions(lines)
    if removed:
        lines = drop_orphan_markers(lines)
        new_text = join_lines(lines, trailing, eol)
        parse_must_work(new_text, a_path)
        write_text(a_path, new_text, bom)
        report.append(f"actions.xml: removed {len(removed)} duplicate "
                      f"definitions ({', '.join(removed)})")
    else:
        report.append("actions.xml: no duplicate actions")

    # ---------- behaviors.xml: rename behaviors to their action -----------
    text, bom, eol = read_text(b_path)
    b_root = parse_must_work(text, b_path)
    action_set = set(action_names)  # names as they exist after the dedupe
    renames = plan_behavior_renames(b_root, action_set)
    if renames:
        lines, trailing = split_lines(text, eol)
        lines = apply_behavior_renames(lines, renames)
        new_text = join_lines(lines, trailing, eol)
        parse_must_work(new_text, b_path)
        write_text(b_path, new_text, bom)
        report.append("behaviors.xml: renamed {} behavior(s) to their "
                      "actions ({})".format(
                          len(renames),
                          ", ".join(f"{o} -> {n}" for o, n in renames.items())))
    else:
        report.append("behaviors.xml: no misreferenced behaviors")

    return report


def main():
    chars = sys.argv[1:] or CHARS
    for char in chars:
        if char not in CHARS:
            raise SystemExit(f"unknown character {char!r} (expected one of {CHARS})")
    for char in chars:
        print(char)
        for line in repair_character(char):
            print(f"  {line}")


if __name__ == "__main__":
    main()
