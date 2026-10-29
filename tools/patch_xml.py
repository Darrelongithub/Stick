#!/usr/bin/env python3
"""Wire the AvA pack into each character's Shimeji-ee conf XML.

Everything (frame counts, anchors, durations, behaviours, frequencies) comes
from tools/ava_common.py, so the XML can never drift from the generator again.
The script is *idempotent by construction*: it deletes everything it owns
(between its own marker comments, plus any older unmarked copy of the same
elements) and writes it back fresh.  Running it twice changes nothing.

It also applies repairs that matter for people who have the pack installed:

* switches ``PullUpShimeji`` off.  That behaviour is Shimeji-ee's breeding
  action: with the stock ``Frequency="50"`` every character clones itself while
  walking, and the only limit is ``totalCount < 50``.  The pack is a four-man
  crew, so cloning actions, behaviours and references are removed entirely.
  The installers also turn off the host app's breeding setting.
* removes the stock, globally selectable Dance behavior and its invalid
  ``<ActionReference Name="Dancing"/>``, then emits one per-character Dance
  weight gated to the actual work-area floor. Dance poses get a stable,
  character-specific beat accent without changing or inventing sprite frames.
* turns the one-frame Stand/StandAffordance statues into phased idle loops,
  caps 20-60 second passive rests, fixes every malformed climb expression,
  and retimes high-displacement stock locomotion for smooth playback.

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
    """Correct missing-call parentheses in every edge-crawl target.

    Both ``ClimbAlongWall`` and ``ClimbIEWall`` contained a branch using
    ``Math.random*100``. Shimeji-ee/ShimeLinux expose ``Math.random`` as a
    function; arithmetic on the function object aborts that branch and makes a
    mascot look stuck to the edge.  Repair only climb action bodies.
    """
    sequence = re.compile(
        r'(<Action\b(?=[^>]*\bName="(?:ClimbAlongWall|ClimbIEWall|ClimbIEBottom)"'
        r')[^>]*>.*?</Action>)', re.S)
    return sequence.sub(
        lambda m: re.sub(r'Math\.random(?!\s*\()', 'Math.random()', m.group(1)), raw)


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


def animate_stand(raw, char):
    """Replace stock one-frame standing statues with the generated idle loop.

    Stand remains a ``Stay`` action because dozens of stock sequences rely on
    its duration override; only its animation changes. StandAffordance (the
    waiting-for-a-hug pose) receives the same treatment and loses the stray
    literal ``\\D\\.png`` text shipped in the source XML.
    """
    eol = eol_of(raw)
    poses = SPEC.poses("Idle", char)
    for action_name in ("Stand", "StandAffordance"):
        action = re.compile(
            r'(?P<head><Action\b(?=[^>]*\bName="' + action_name + r'")[^>]*>)'
            r'(?P<body>.*?)(?P<tail></Action>)', re.S)
        match = action.search(raw)
        if not match:
            continue
        line_start = raw.rfind("\n", 0, match.start("head")) + 1
        indent = raw[line_start:match.start("head")]
        lines = [indent + "\t<Animation>"]
        for i, (img, anc, vel, dur) in enumerate(poses):
            dur = SPEC.duration_for("Idle", char, i, dur)
            lines.append(indent + "\t\t" + pose_line(eol, img, anc, vel, dur).lstrip())
        lines.append(indent + "\t</Animation>")
        body = eol + eol.join(lines) + eol + indent
        raw = (raw[:match.end("head")] + body
               + match.group("tail") + raw[match.end("tail"):])
    return raw


# A 500-1500 tick stock rest is 20-60 seconds of apparent inactivity.  Keep
# rests, but cap them to a few seconds so active behaviours get another turn.
REST_LIMITS = {
    "Stand": (18, 32),              # 0.7-2.0 s, breathing throughout
    "Sit": (30, 55),                # 1.2-3.4 s
    "Sprawl": (35, 65),             # 1.4-4.0 s
    "SitWithLegsDown": (24, 42),
    "SitAndDangleLegs": (35, 55),
    "GrabWall": (30, 50),
    "GrabCeiling": (30, 50),
}


def shorten_long_rests(raw):
    ref = re.compile(r'<ActionReference\b[^>]*/>')
    duration = re.compile(
        r'Duration="\$\{(?P<base>\d+)\+Math\.random\(\)\*(?P<spread>\d+)\}"')

    def cap(match):
        tag = match.group(0)
        name_match = re.search(r'\bName="(' + "|".join(map(re.escape, REST_LIMITS)) + r')"', tag)
        value = duration.search(tag)
        if not name_match or not value:
            return tag
        if int(value.group("base")) + int(value.group("spread")) <= 120:
            return tag
        new_base, new_spread = REST_LIMITS[name_match.group(1)]
        replacement = f'Duration="${{{new_base}+Math.random()*{new_spread}}}"'
        return tag[:value.start()] + replacement + tag[value.end():]

    return ref.sub(cap, raw)


# Stock locomotion jumped as much as 18 px on every 40ms host tick.  More frame
# changes with smaller per-tick displacement preserves energy without judder.
STOCK_MOTION = {
    "Blue":   {"Walk": (-3, 2), "Run": (-8, 1), "Dash": (-10, 1),
               "RunAffordance": (-10, 1)},
    "Orange": {"Walk": (-4, 2), "Run": (-11, 1), "Dash": (-13, 1),
               "RunAffordance": (-13, 1)},
    "Yellow": {"Walk": (-3, 2), "Run": (-9, 1), "Dash": (-11, 1),
               "RunAffordance": (-11, 1)},
    "Green":  {"Walk": (-3, 2), "Run": (-10, 1), "Dash": (-12, 1),
               "RunAffordance": (-12, 1)},
}


def smooth_stock_motion(raw, char):
    for name, (vx, duration) in STOCK_MOTION[char].items():
        action = re.compile(
            r'(<Action\b(?=[^>]*\bName="' + re.escape(name) + r'")[^>]*>.*?</Action>)',
            re.S)

        def tune(match):
            body = re.sub(r'Velocity="-?\d+,0"', f'Velocity="{vx},0"', match.group(1))
            return re.sub(r'Duration="\d+"', f'Duration="{duration}"', body)

        raw = action.sub(tune, raw, count=1)
    return raw


# Lower the stock 20-60 second rest paths and give locomotion different odds
# per character.  Generated moves now compete fairly instead of losing every
# decision to a Frequency=1000 HugSearch or two Frequency=200 static rests.
STOCK_BEHAVIOR_WEIGHTS = {
    "Blue":   {"SitAndFaceMouse": 7, "StandUp": 24, "SitDown": 13,
               "SitWhileDanglingLegs": 10, "LieDown": 7, "HugAffordance": 8,
               "HugSearch": 18, "WalkAlongWorkAreaFloor": 34,
               "RunAlongWorkAreaFloor": 12, "ClimbHalfwayAlongWall": 22,
               "ClimbAlongWall": 18, "ClimbAlongCeiling": 36},
    "Orange": {"SitAndFaceMouse": 5, "StandUp": 12, "SitDown": 8,
               "SitWhileDanglingLegs": 6, "LieDown": 4, "HugAffordance": 14,
               "HugSearch": 22, "WalkAlongWorkAreaFloor": 18,
               "RunAlongWorkAreaFloor": 42, "ClimbHalfwayAlongWall": 14,
               "ClimbAlongWall": 26, "ClimbAlongCeiling": 16},
    "Yellow": {"SitAndFaceMouse": 9, "StandUp": 18, "SitDown": 11,
               "SitWhileDanglingLegs": 12, "LieDown": 5, "HugAffordance": 10,
               "HugSearch": 16, "WalkAlongWorkAreaFloor": 30,
               "RunAlongWorkAreaFloor": 21, "ClimbHalfwayAlongWall": 34,
               "ClimbAlongWall": 38, "ClimbAlongCeiling": 14},
    "Green":  {"SitAndFaceMouse": 8, "StandUp": 20, "SitDown": 16,
               "SitWhileDanglingLegs": 14, "LieDown": 8, "HugAffordance": 16,
               "HugSearch": 20, "WalkAlongWorkAreaFloor": 27,
               "RunAlongWorkAreaFloor": 27, "ClimbHalfwayAlongWall": 20,
               "ClimbAlongWall": 24, "ClimbAlongCeiling": 28},
}

# The remaining floor/window routes were all Frequency=100 in identical order.
# Give each character a different low-weight route profile so those stock
# sequences cannot swamp the richer generated pool or march in lockstep.
SECONDARY_STOCK_BEHAVIORS = (
    "WalkLeftAlongFloorAndSit", "WalkRightAlongFloorAndSit",
    "GrabWorkAreaBottomLeftWall", "GrabWorkAreaBottomRightWall",
    "WalkLeftAndSit", "WalkRightAndSit",
    "RunAndGrabBottomLeftWall", "RunAndGrabBottomRightWall",
    "WalkAlongIECeiling", "RunAlongIECeiling",
    "SitOnTheLeftEdgeOfIE", "SitOnTheRightEdgeOfIE",
    "WalkLeftAlongIEAndSit", "WalkRightAlongIEAndSit",
    "WalkLeftAlongIEAndJump", "WalkRightAlongIEAndJump",
)
SECONDARY_STOCK_PROFILES = {
    "Blue":   (12, 7, 6, 9, 11, 5, 5, 8, 14, 6, 7, 10, 9, 5, 6, 8),
    "Orange": (6, 11, 5, 8, 4, 9, 15, 10, 5, 14, 4, 7, 5, 9, 13, 8),
    "Yellow": (10, 6, 13, 7, 8, 12, 6, 11, 12, 8, 11, 5, 10, 6, 7, 13),
    "Green":  (8, 13, 7, 10, 12, 6, 9, 14, 9, 13, 6, 12, 7, 11, 10, 5),
}
for _char, _profile in SECONDARY_STOCK_PROFILES.items():
    STOCK_BEHAVIOR_WEIGHTS[_char].update(zip(SECONDARY_STOCK_BEHAVIORS, _profile))


def retune_stock_behaviors(raw, char):
    for name, frequency in STOCK_BEHAVIOR_WEIGHTS[char].items():
        element = re.compile(
            r'(<Behavior\b(?=[^>]*\bName="' + re.escape(name)
            + r'")[^>]*?\bFrequency=")\d+("[^>]*>)')
        raw = element.sub(rf'\g<1>{frequency}\2', raw, count=1)
    return raw


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


def action_xml(name, eol, char):
    """The <Action> element for a generated action, personality timing included."""
    spec = SPEC.ACTIONS[name]
    attrs = [f'Name="{name}"', f'Type="{spec["type"]}"']
    if spec.get("border"):
        attrs.append(f'BorderType="{spec["border"]}"')
    if spec.get("loop"):
        attrs.append(f'Loop="{spec["loop"]}"')
    for k, v in (spec.get("embed") or {}).items():
        attrs.append(f'{k}="{v}"')
    head = "\t\t<Action " + " ".join(attrs) + ">"
    poses = single_pass(name, SPEC.poses(name, char))
    poses = [(img, anc, vel, SPEC.duration_for(name, char, i, dur))
             for i, (img, anc, vel, dur) in enumerate(poses)]
    body = [pose_line(eol, img, anc, vel, dur)
            for img, anc, vel, dur in poses]
    lines = [head, "\t\t\t<Animation>"] + body + ["\t\t\t</Animation>", "\t\t</Action>"]
    if spec.get("two_animations"):
        # Climb up in authored order and descend through the 48-frame cycle in
        # reverse with matching positive velocity; reusing the up-cycle while
        # moving down made the contacting feet and hands snap backward.
        cond_up = '#{TargetY &lt; mascot.anchor.y}'
        cond_dn = '#{TargetY &gt;= mascot.anchor.y}'
        def reverse_vertical(velocity):
            x, y = velocity.split(",", 1)
            return f"{x},{-int(y)}"

        down = [pose_line(eol, img, anc, reverse_vertical(vel), dur)
                for img, anc, vel, dur in reversed(poses)]
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
    signature_defaults = dict(SPEC.signature_behaviors(char))
    if name in signature_defaults:
        freq = freq or signature_defaults[name]
    cond = SPEC.condition(name) or SPEC.gate(name)
    cond_attr = f' Condition="{esc(cond)}"' if cond else ""
    return f'\t\t<Behavior Name="{name}" Frequency="{freq}"{cond_attr} />'


def generated_names(char):
    """Every action/behaviour this character gets, in emit order."""
    return SPEC.generated_actions_for(char) + list(SPEC.SEQUENCES)


def behavior_names(char):
    names = [n for n, _f, _g, _c in SPEC.BEHAVIORS if SPEC.freq(n, char) > 0]
    for sig, _freq in SPEC.signature_behaviors(char):
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
    block = [A_START] + [action_xml(n, eol, char)
                         for n in SPEC.generated_actions_for(char)]
    block += [sequence_xml(n, eol) for n in SPEC.SEQUENCES]
    block += [A_END]
    if "</ActionList>" not in raw:
        raise SystemExit(f"REFUSING to patch {path}: no </ActionList>")
    # generated actions go into the FIRST <ActionList> (the files have two,
    # and Shimeji-ee rejects duplicate action names).
    raw = insert_before_line(raw, "</ActionList>", eol.join(block), eol)
    raw = fix_crawl_sequence_expressions(raw)
    raw = retime_dance(raw, char)
    raw = smooth_stock_motion(raw, char)
    raw = shorten_long_rests(raw)
    raw = animate_stand(raw, char)
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
    raw = retune_stock_behaviors(raw, char)
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
