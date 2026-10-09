#!/usr/bin/env python3
"""Wire the AvA pack into each character's Shimeji-ee conf XML.

Everything (frame counts, anchors, durations, behaviours, frequencies) comes
from tools/ava_common.py, so the XML can never drift from the generator again.
The script is *idempotent by construction*: it deletes everything it owns
(between its own marker comments, plus any older unmarked copy of the same
elements) and writes it back fresh.  Running it twice changes nothing.

It also does two repairs that matter for people who have the pack installed:

* switches ``PullUpShimeji`` off.  That behaviour is Shimeji-ee's breeding
  action: with the stock ``Frequency="50"`` every character clones itself while
  walking, and the only limit is ``totalCount < 50``.  The pack is a four-man
  crew, so the behaviour is pinned to Frequency="0" and the app-level
  ``Breeding`` flag is turned off as well.
* removes the stock ``<ActionReference Name="Dancing"/>`` inside ``<Behavior
  Name="Dance">`` and the duplicated Dance behaviours, which Shimeji-ee cannot
  resolve (it looks a behaviour's action up by the behaviour's own Name and
  logs "no corresponding action Dancing").

Usage:
    python3 tools/patch_xml.py            # patch every character
    python3 tools/patch_xml.py Blue       # just one
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ava_common as SPEC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

A_START = "\t\t<!-- AVA:generated:actions:start -->"
A_END = "\t\t<!-- AVA:generated:actions:end -->"
B_START = "\t\t<!-- AVA:generated:behaviors:start -->"
B_END = "\t\t<!-- AVA:generated:behaviors:end -->"

# Elements this script owns: anything a previous *unmarked* run of the tool
# (or the original handwritten patch) left behind.
REMOVABLE_ACTIONS = set(SPEC.ACTIONS) | set(SPEC.SEQUENCES)
REMOVABLE_BEHAVIORS = set(SPEC.ACTIONS) | set(SPEC.SEQUENCES) | {"Dance", "Trip"}


def read(path):
    with open(path, "rb") as fh:
        raw = fh.read().decode("utf-8")
    return raw


def write(path, raw):
    with open(path, "wb") as fh:
        fh.write(raw.encode("utf-8"))


def eol_of(raw):
    return "\r\n" if "\r\n" in raw else "\n"


def insert_before_line(raw, needle, text, eol):
    """Insert `text` on its own line(s) immediately before the line holding
    `needle`.  Anchoring on the line start (instead of on the needle itself)
    is what makes repeated patches byte-identical: the result no longer
    depends on whatever indentation used to sit before the needle."""
    idx = raw.index(needle)
    line_start = raw.rfind("\n", 0, idx) + 1
    return raw[:line_start] + text + eol + raw[line_start:]


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- removal
def strip_block(raw, start, end):
    """Drop a generated block together with the blank lines that held it, so
    re-patching is byte-identical instead of growing a blank line per run."""
    pat = re.compile(r"[ \t]*" + re.escape(start) + r".*?" + re.escape(end)
                     + r"[ \t]*\r?\n", re.S)
    return pat.sub("", raw)


def strip_elements(raw, tag, names):
    """Drop every `<tag ... Name="name" ...>` element for the given names.

    Element-scoped, so `<ActionReference Name="Wave"/>` inside some sequence is
    never touched.  Elements have no nested same-tag children in these files,
    so "start tag .. first close tag" is exact here.
    """
    for name in sorted(names, key=len, reverse=True):
        start_re = re.compile(
            r'[ \t]*<' + tag + r'\b[^>]*?\bName="' + re.escape(name) + r'"[^>]*?/?>')
        while True:
            m = start_re.search(raw)
            if not m:
                break
            tag_end = raw.find(">", m.start()) + 1
            if raw[m.start():tag_end].rstrip().endswith("/>"):
                end = tag_end
            else:
                close = raw.find("</" + tag + ">", tag_end)
                if close == -1:
                    break
                end = close + len(tag) + 3
            # swallow the newline(s) the element occupied
            while end < len(raw) and raw[end] in "\r\n":
                end += 1
            raw = raw[:m.start()] + raw[end:]
    return raw


def fix_dance(raw):
    """Stock Dance behaviour: drop an ActionReference Shimeji-ee cannot use and
    any duplicated Dance behaviours, keeping exactly one Frequency=10 entry."""
    eol = eol_of(raw)
    raw = re.sub(r'[ \t]*<ActionReference Name="Dancing"\s*/>\r?\n?', "", raw)
    pat = re.compile(r'[ \t]*<Behavior Name="Dance"[^>]*?/>\r?\n?')
    first = True

    def keep(m):
        nonlocal first
        if first:
            first = False
            return f'\t\t<Behavior Name="Dance" Frequency="10" />{eol}'
        return ""

    return pat.sub(keep, raw)


# Everything that can make a copy of a character.  Shimeji-ee breeds through an
# Embedded `Breed` action (PullUpShimeji1) reached only from the PullUpShimeji
# behaviour.  Pinning that behaviour's frequency to 0 was not enough: libshijima
# still picks a zero-weight entry when it is the only candidate left, so the
# behaviour, every reference to it and the Breed action itself are removed.
BREED_ACTIONS = {"PullUpShimeji", "PullUpShimeji1", "PullUpShimeji2"}


def disable_breeding(raw):
    for name in SPEC.DISABLED_BEHAVIORS:
        raw = strip_elements(raw, "Behavior", {name})
        raw = strip_elements(raw, "BehaviorReference", {name})
    raw = strip_elements(raw, "Action", BREED_ACTIONS)
    raw = strip_elements(raw, "ActionReference", BREED_ACTIONS)
    return raw


# ---------------------------------------------------------------- emitting
def pose_line(eol, image, anchor, velocity, duration):
    return (f'\t\t\t\t<Pose Image="/{image}" ImageAnchor="{anchor}" '
            f'Velocity="{velocity}" Duration="{duration}" />')


# Actions whose frames are meant to go back and forth (the sleep breath).
REVISIT_BY_DESIGN = {"Sleep"}


def single_pass(name, poses):
    """Stop an action re-playing its own frames.

    Several generated actions bounce between the same two or three frames
    (Wave: 1,2,3,4,3,4,1), which reads as the same move repeated several
    times inside one action.  A revisit is folded into the frame's first
    visit - its ticks are added to that visit - so the action keeps its total
    length but each frame appears once.  Moving actions are left alone:
    folding would change how far the character travels.
    """
    if name in REVISIT_BY_DESIGN or any(vel != "0,0" for _, _, vel, _ in poses):
        return list(poses)
    out, first = [], {}
    for img, anc, vel, dur in poses:
        if img in first:
            i = first[img]
            o_img, o_anc, o_vel, o_dur = out[i]
            out[i] = (o_img, o_anc, o_vel, o_dur + dur)
        else:
            first[img] = len(out)
            out.append((img, anc, vel, dur))
    return out


def action_xml(name, eol):
    """The <Action> element for a generated action."""
    spec = SPEC.ACTIONS[name]
    attrs = [f'Name="{name}"', f'Type="{spec["type"]}"']
    if spec.get("border"):
        attrs.append(f'BorderType="{spec["border"]}"')
    if spec.get("loop"):
        attrs.append(f'Loop="{spec["loop"]}"')
    for k, v in (spec.get("embed") or {}).items():
        attrs.append(f'{k}="{v}"')
    head = "\t\t<Action " + " ".join(attrs) + ">"
    body = [pose_line(eol, img, anc, vel, dur)
            for img, anc, vel, dur in single_pass(name, SPEC.poses(name))]
    lines = [head, "\t\t\t<Animation>"] + body + ["\t\t\t</Animation>", "\t\t</Action>"]
    if spec.get("two_animations"):
        # ClimbWall is direction-dependent upstream: emit the same animation
        # twice with the stock conditions, so up- and down-climbing both work.
        cond_up = '#{TargetY &lt; mascot.anchor.y}'
        cond_dn = '#{TargetY &gt;= mascot.anchor.y}'
        inner = "\n".join(body)
        anims = [f"\t\t\t<Animation Condition=\"{cond_up}\">",
                 inner, "\t\t\t</Animation>",
                 f"\t\t\t<Animation Condition=\"{cond_dn}\">",
                 inner, "\t\t\t</Animation>"]
        lines = [head] + anims + ["\t\t</Action>"]
    return eol.join(lines)


def sequence_xml(name, eol):
    refs = SPEC.SEQUENCES[name]
    lines = [f'\t\t<Action Name="{name}" Type="Sequence" Loop="false">']
    lines += [f'\t\t\t<ActionReference Name="{r}" />' for r in refs]
    lines.append("\t\t</Action>")
    return eol.join(lines)


def behavior_xml(name, char, eol):
    freq = SPEC.freq(name, char)
    if name == SPEC.SIG_BEHAVIORS[char][0]:
        freq = SPEC.freq(name, char) or SPEC.SIG_BEHAVIORS[char][1]
    cond = SPEC.condition(name) or SPEC.gate(name)
    cond_attr = f' Condition="{esc(cond)}"' if cond else ""
    return f'\t\t<Behavior Name="{name}" Frequency="{freq}"{cond_attr} />'


def generated_names(char):
    """Every action/behaviour this character gets, in emit order."""
    return SPEC.generated_actions_for(char) + list(SPEC.SEQUENCES)


def behavior_names(char):
    names = [n for n, _f, _g, _c in SPEC.BEHAVIORS if SPEC.freq(n, char) > 0]
    sig = SPEC.SIG_BEHAVIORS[char][0]
    if sig not in names:
        names.append(sig)
    return names


# ---------------------------------------------------------------- drivers
def patch_actions(path, char):
    raw = read(path)
    eol = eol_of(raw)
    raw = disable_breeding(raw)
    raw = strip_block(raw, A_START, A_END)
    # sequences are ours too - strip them, or re-running duplicates them
    raw = strip_elements(raw, "Action", REMOVABLE_ACTIONS)
    # only this character's actions (signature moves belong to one character)
    block = [A_START] + [action_xml(n, eol) for n in SPEC.generated_actions_for(char)]
    block += [sequence_xml(n, eol) for n in SPEC.SEQUENCES]
    block += [A_END]
    if "</ActionList>" not in raw:
        raise SystemExit(f"REFUSING to patch {path}: no </ActionList>")
    # generated actions go into the FIRST <ActionList> (the files have two,
    # and Shimeji-ee rejects duplicate action names).
    raw = insert_before_line(raw, "</ActionList>", eol.join(block), eol)
    write(path, raw)
    print(f"  {path}: {len(SPEC.generated_actions_for(char))} actions, "
          f"{len(SPEC.SEQUENCES)} sequences")


def patch_behaviors(path, char):
    raw = read(path)
    eol = eol_of(raw)
    raw = strip_block(raw, B_START, B_END)
    raw = strip_elements(raw, "Behavior", {n for n in REMOVABLE_BEHAVIORS
                                           if n not in ("Dance", "Trip")})
    raw = fix_dance(raw)
    raw = disable_breeding(raw)
    block = ([B_START]
             + [behavior_xml(n, char, eol) for n in behavior_names(char)]
             + [B_END])
    if "</BehaviorList>" not in raw:
        raise SystemExit(f"REFUSING to patch {path}: no </BehaviorList>")
    raw = insert_before_line(raw, "</BehaviorList>", eol.join(block), eol)
    write(path, raw)
    print(f"  {path}: {len(behavior_names(char))} behaviours "
          f"(breeding off)")


def patch_char(char):
    print(char)
    patch_actions(os.path.join(ROOT, "AVA Shimejis", char, "conf", "actions.xml"), char)
    patch_behaviors(os.path.join(ROOT, "AVA Shimejis", char, "conf", "behaviors.xml"), char)


def main():
    SPEC.self_check()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    for char in (args or SPEC.CHARS):
        if char not in SPEC.CHARS:
            raise SystemExit(f"unknown character {char!r}")
        patch_char(char)


if __name__ == "__main__":
    main()
