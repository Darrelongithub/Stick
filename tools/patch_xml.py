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
  crew, so cloning actions, behaviours and references are removed entirely.
  The installers also turn off the host app's breeding setting.
* removes the stock, globally selectable Dance behavior and its invalid
  ``<ActionReference Name="Dancing"/>``, then emits one per-character Dance
  weight gated to the actual work-area floor. Dance poses get a stable,
  character-specific beat accent without changing or inventing sprite frames.

Usage:
    python3 tools/patch_xml.py            # patch every character
    python3 tools/patch_xml.py Blue       # just one
"""
import os
import random
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
    """Remove malformed/duplicate stock Dance entries.

    The original Dance behavior was globally selectable (including while a
    mascot was hanging or falling), despite its Floor-bounded action. The
    correctly gated Dance behavior is emitted with the generated behavior pool.
    """
    raw = re.sub(r'[ \t]*<ActionReference Name="Dancing"\s*/>\r?\n?', "", raw)
    dance = re.compile(
        r'[ \t]*<Behavior\b(?=[^>]*\bName="Dance")[^>]*/>\r?\n?'
        r'|[ \t]*<Behavior\b(?=[^>]*\bName="Dance")[^>]*>.*?</Behavior>\r?\n?',
        re.S)
    return dance.sub("", raw)


def fix_crawl_sequence_expressions(raw):
    """Correct the missing-call parentheses in ClimbAlongWall's target.

    Shimeji-ee/ShimeLinux expose Math.random() as a function; subtracting the
    function object itself is not a valid target expression. Keep this repair
    scoped to the wall-crawl sequence rather than rewriting unrelated actions.
    """
    sequence = re.compile(
        r'(<Action\b(?=[^>]*\bName="ClimbAlongWall")[^>]*>.*?</Action>)', re.S)
    return sequence.sub(lambda m: m.group(1).replace("Math.random*100", "Math.random()*100"), raw)


def retime_dance(raw, char):
    """Apply one stable character-specific beat accent to Dance's existing
    frames, leaving its poses and choreography intact. A marker makes patching
    idempotent, and frame filenames remain untouched.
    """
    marker = f"<!-- AVA:dance-tempo:{char} -->"
    already_timed = marker in raw
    action = re.compile(
        r'(<Action\b(?=[^>]*\bName="Dance")[^>]*>)(.*?)(</Action>)', re.S)
    match = action.search(raw)
    if not match:
        return raw
    accents = SPEC.DANCE_TEMPO_ACCENTS[char]
    index = 0

    def accent_pose(pose):
        nonlocal index
        accent = accents[index % len(accents)]
        index += 1
        return re.sub(r'Duration="(\d+)"',
                      lambda m: f'Duration="{int(m.group(1)) + accent}"',
                      pose.group(0), count=1)

    body = (match.group(2) if already_timed else
            re.sub(r'<Pose\b[^>]*/>', accent_pose, match.group(2)))
    opening = match.group(1)
    if "Condition=" not in opening:
        opening = opening[:-1] + ' Condition="#{mascot.environment.floor.isOn(mascot.anchor)}">'
    updated = (raw[:match.start(1)] + opening + body + match.group(3)
               + raw[match.end(3):])
    if already_timed:
        return updated
    # Put the marker on its own line above the action, preserving indentation.
    start = match.start(1)
    line_start = updated.rfind("\n", 0, start) + 1
    indent = updated[line_start:start]
    eol = eol_of(updated)
    return updated[:line_start] + indent + marker + eol + updated[line_start:]


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
    poses = single_pass(name, SPEC.poses(name))
    body = [pose_line(eol, img, anc, vel, dur)
            for img, anc, vel, dur in poses]
    lines = [head, "\t\t\t<Animation>"] + body + ["\t\t\t</Animation>", "\t\t</Action>"]
    if spec.get("two_animations"):
        # The wall sprite set has five existing poses. Climb up in authored
        # order and descend in reverse with the matching positive velocity;
        # reusing the up-cycle while moving down made the feet/arms snap back.
        cond_up = '#{TargetY &lt; mascot.anchor.y}'
        cond_dn = '#{TargetY &gt;= mascot.anchor.y}'
        down = [pose_line(eol, img, anc, "0,3", dur)
                for img, anc, _vel, dur in reversed(poses)]
        anims = [f"\t\t\t<Animation Condition=\"{cond_up}\">",
                 eol.join(body), "\t\t\t</Animation>",
                 f"\t\t\t<Animation Condition=\"{cond_dn}\">",
                 eol.join(down), "\t\t\t</Animation>"]
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
    # The selection pool is weighted, but order also maps the random chooser's
    # cumulative intervals. A stable per-character shuffle avoids identical
    # ordering while keeping generated XML reproducible.
    random.Random("ava-behavior-pool-" + char).shuffle(names)
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
    raw = fix_crawl_sequence_expressions(raw)
    raw = retime_dance(raw, char)
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
