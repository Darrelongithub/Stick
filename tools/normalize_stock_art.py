#!/usr/bin/env python3
"""Give every character's *original pack* art the same figure scale.

The bug this fixes
------------------
A mascot changes size the moment one kind of animation starts and goes back to
normal when the next one begins.  Measured, the pack has two different drawing
scales:

    frame        Blue        Yellow      Green       Orange
    idle01.png   24px head   24px head   24px head   24px head   (generated)
    stand01.png  24px head   24px head   24px head   37px head   (original)
                 110px tall  110px tall  110px tall  125px tall

Every *generated* frame (``stickgen``) is drawn at one scale for all four
characters - 24px head, 110px tall.  Blue, Yellow and Green's original-pack
frames match it.  Orange's do not: they are the same body at ~1.14x with a
head nearly 1.5x the size (and hollow, where every other frame in the pack is
filled).  So Orange alone reads bigger while it walks, runs, sits, dances,
bounces or hugs, and snaps back to normal on its next generated move.

The fix is to normalise a character's original-pack frames - and only the ones
whose measured scale is off, so a character's own variant art (Yellow's
reading pose, Green's dancing, ...) is left exactly as drawn, because those are
the right size already.  Frames are re-rendered from the shared original,
recoloured to the character's own body colour, so the result is pixel-identical
in proportion to every other animation the character can play.

Usage
    python3 tools/normalize_stock_art.py           # measure, then fix in place
    python3 tools/normalize_stock_art.py --check   # measure and report only
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ava_common as SPEC  # noqa: E402

ROOT = os.path.dirname(HERE)
PACK = os.path.join(ROOT, "AVA Shimejis")

# Same values stickgen draws with, so a recoloured frame is indistinguishable
# from a generated one.
BODY = {
    "Blue": (37, 192, 255),
    "Orange": (242, 111, 36),
    "Yellow": (255, 197, 0),
    "Green": (95, 183, 0),
}
SOURCE = "Blue"
TOL = 42

# A character whose stock frames are within this much of the shared original is
# considered the same drawing and is left untouched.
SCALE_TOLERANCE = 0.06

# Poses whose ImageAnchor differs from the shared original's.  Orange's Dance
# was drawn on a 128x137 canvas with its anchor on the bottom row (64,137);
# the shared original is 128x128 anchored at (64,128).  Replacing the art
# makes the old anchor sink the figure 9px below the floor line.
ANCHOR_FIXES = {"Orange": {"Dance": "64,128"}}

NS = "{http://www.group-finity.com/Mascot}"

# The pack's XML is UTF-8 with a byte-order mark and CRLF line endings on
# purpose (.gitattributes marks the CR), so anchor edits must preserve both or
# the whole file shows up as rewritten.
BOM = b"\xef\xbb\xbf"


def read_conf(path):
    """(text, had_bom) with the BOM stripped so it can be re-added cleanly."""
    with open(path, "rb") as handle:
        data = handle.read()
    had_bom = data.startswith(BOM)
    return data.decode("utf-8-sig" if had_bom else "utf-8"), had_bom


def write_conf(path, text, had_bom):
    with open(path, "wb") as handle:
        handle.write((BOM if had_bom else b"") + text.encode("utf-8"))


def generated_names():
    names = set()
    for action, spec in SPEC.ACTIONS.items():
        names.update(SPEC.frame_names(action))
        names.update(spec.get("files", ()))
    return names


def stock_images(char):
    """Original-pack frames this character's XML actually references."""
    generated = generated_names()
    path = os.path.join(PACK, char, "conf", "actions.xml")
    names = []
    for pose in ET.parse(path).getroot().iter(NS + "Pose"):
        image = (pose.get("Image") or "").lstrip("/")
        if image and image not in generated and image not in names:
            names.append(image)
    return names


def stock_frames(char):
    """Every original-pack frame in the folder, referenced or not.

    The whole set is normalised together so an animation that is currently
    unused cannot reintroduce the same size jump later; generated frames are
    excluded because stickgen owns them.
    """
    generated = generated_names()
    return [name for name in sorted(os.listdir(os.path.join(PACK, char)))
            if name.endswith(".png") and name not in generated]


def body_rows(image, rgb):
    """(top, bottom) of the body-coloured pixels, or None."""
    pixels = image.load()
    w, h = image.size
    rows = [y for y in range(h)
            if any(pixels[x, y][3] > 110
                   and abs(pixels[x, y][0] - rgb[0]) <= TOL
                   and abs(pixels[x, y][1] - rgb[1]) <= TOL
                   and abs(pixels[x, y][2] - rgb[2]) <= TOL
                   for x in range(w))]
    return (rows[0], rows[-1]) if rows else None


def figure_scale(image, rgb):
    """Figure height in pixels: the anchor-independent measure of scale."""
    rows = body_rows(image, rgb)
    return None if rows is None else rows[1] - rows[0] + 1


def compare_frames(char):
    """Original-pack frames, with each character's figure height next to Blue's.

    Only frames this character's XML pulls from the original pack are measured:
    generated frames are identical for every character by construction, so
    including them would dilute the median towards 1.0 and hide the very
    difference this tool exists to find.
    """
    scales = {}
    for name in stock_images(char):
        path = os.path.join(PACK, SOURCE, name)
        other_path = os.path.join(PACK, char, name)
        if not (os.path.isfile(path) and os.path.isfile(other_path)):
            continue
        reference = figure_scale(Image.open(path).convert("RGBA"), BODY[SOURCE])
        value = figure_scale(Image.open(other_path).convert("RGBA"), BODY[char])
        if reference and value and reference > 30:
            scales[name] = {SOURCE: reference, char: value}
    return scales


def measure_characters():
    """Per character: median size ratio of its original-pack art vs Blue's."""
    measured = {}
    for char in SPEC.CHARS:
        if char == SOURCE:
            continue
        scales = compare_frames(char)
        ratios = [row[char] / row[SOURCE] for row in scales.values()]
        measured[char] = (statistics.median(ratios) if ratios else 1.0, len(ratios))
    return measured


def recolour(image, src_rgb, dst_rgb):
    """Blue body pixels -> this character's body colour; props stay as they are."""
    out = image.copy()
    pixels = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            pixel = pixels[x, y]
            if (pixel[3] > 0
                    and abs(pixel[0] - src_rgb[0]) <= TOL
                    and abs(pixel[1] - src_rgb[1]) <= TOL
                    and abs(pixel[2] - src_rgb[2]) <= TOL):
                pixels[x, y] = dst_rgb + (pixel[3],)
    return out


def source_for(name, originals):
    """The shared original for `name`, or the closest one that exists.

    Only ``dance90.png`` has no same-named original (Orange's dance loop is one
    frame longer), so it takes the last shared beat.
    """
    if name in originals:
        return originals[name]
    stem = re.sub(r"(\d+)\.png$", "", name)
    siblings = [n for n in originals if re.sub(r"(\d+)\.png$", "", n) == stem]
    if not siblings:
        return None
    wanted = int(re.search(r"(\d+)\.png$", name).group(1))
    best = min(siblings,
               key=lambda n: abs(int(re.search(r"(\d+)\.png$", n).group(1)) - wanted))
    return originals[best]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="measure and report, write nothing")
    args = parser.parse_args(argv)

    src_dir = os.path.join(PACK, SOURCE)
    originals = {name: Image.open(os.path.join(src_dir, name)).convert("RGBA")
                 for name in sorted(os.listdir(src_dir)) if name.endswith(".png")}

    measured = measure_characters()
    offenders = {char: ratio for char, (ratio, _n) in measured.items()
                 if abs(ratio - 1.0) > SCALE_TOLERANCE}
    for char, (ratio, count) in measured.items():
        verdict = "normalising" if char in offenders else "left alone"
        print(f"  {char}: original-pack art is {ratio:.3f}x the shared original"
              f" (n={count} frames) - {verdict}")
    if not offenders:
        print("figure scale: already consistent")

    changed = 0
    for char in offenders:
        directory = os.path.join(PACK, char)
        for name in stock_frames(char):
            original = source_for(name, originals)
            target = os.path.join(directory, name)
            if original is None or not os.path.isfile(target):
                print(f"  {char}/{name}: no shared original, left alone")
                continue
            current = Image.open(target).convert("RGBA")
            # Written on the shared original's own canvas: the old, oversized
            # drawings needed extra margin that the correct figure does not, and
            # keeping it would leave the two characters on different canvases.
            fixed = recolour(original, BODY[SOURCE], BODY[char])
            if current.tobytes() == fixed.tobytes():
                continue
            changed += 1
            if not args.check:
                fixed.save(target)
        print(f"  {char}: {changed} frame(s) so far")

    # Anchors are checked whenever the shared art is in use - including on a
    # later run, when the scale already matches and no frame is rewritten.
    for char, actions in ANCHOR_FIXES.items():
        path = os.path.join(PACK, char, "conf", "actions.xml")
        raw, had_bom = read_conf(path)
        updated = raw
        for action, anchor in actions.items():
            pattern = re.compile(
                r'(<Action\b(?=[^>]*\bName="' + re.escape(action) + r'")[^>]*>.*?</Action>)',
                re.S)

            def rewrite(match, anchor=anchor):
                return re.sub(r'ImageAnchor="[^"]*"', f'ImageAnchor="{anchor}"',
                              match.group(1))

            updated = pattern.sub(rewrite, updated, count=1)
        if updated != raw:
            print(f"  {char}/conf/actions.xml: anchors -> {actions}")
            changed += 1
            if not args.check:
                write_conf(path, updated, had_bom)

    print(f"{changed} file(s) {'would change' if args.check else 'changed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
