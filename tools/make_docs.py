#!/usr/bin/env python3
"""Regenerate the images in docs/ (the ones the README shows).

    python3 tools/make_docs.py

Needs Pillow.  Nothing here affects the pack itself - it only draws contact
sheets out of the frames in AVA Shimejis/, so the README can never show
something the generator no longer produces.
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ava_common as SPEC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
BG = (26, 28, 34)
FG = (240, 240, 245)
ACC = (120, 200, 255)


def frame(char, name):
    return Image.open(os.path.join(ROOT, "AVA Shimejis", char, name)).convert("RGBA")


def checker(w, h, size=8, c1=(58, 60, 68), c2=(46, 48, 56)):
    im = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(im)
    for y in range(0, h, size):
        for x in range(0, w, size):
            if (x // size + y // size) % 2 == 0:
                d.rectangle([x, y, x + size - 1, y + size - 1], fill=c2)
    return im


def cell(im, scale=1):
    c = checker(*im.size)
    c.paste(im, (0, 0), im)
    if scale != 1:
        c = c.resize((int(im.width * scale), int(im.height * scale)), Image.NEAREST)
    return c


def hero():
    picks = {"Blue": "wave03.png", "Orange": "fight_punch01.png",
             "Yellow": "tinker02.png", "Green": "music02.png"}
    S, PAD, LBL = 2, 14, 26
    W = PAD + len(picks) * (160 * S + PAD)
    H = PAD + LBL + 160 * S + PAD
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    for i, (ch, fn) in enumerate(picks.items()):
        x, y = PAD + i * (160 * S + PAD), PAD + LBL
        sheet.paste(cell(frame(ch, fn), S), (x, y))
        d.text((x + 2, y - 18), f"{ch}  ({fn})", fill=FG)
    sheet.save(os.path.join(DOCS, "hero.png"), optimize=True)


def new_moves():
    picks = [("Idle", "idle02.png"), ("Stretch", "stretch03.png"), ("Taunt", "taunt04.png"),
             ("SpinKick", "spin03.png"), ("Phone", "phone03.png"), ("Coffee", "coffee03.png"),
             ("Meditate", "meditate02.png"), ("Cry", "cry03.png"), ("Dizzy", "dizzy02.png"),
             ("Juggle", "juggle01.png"), ("Victory", "victory03.png"),
             ("Falling", "fall02.png"), ("GrabCeiling", "hang02.png"),
             ("ClimbCeiling", "swing03.png"), ("GrabWall", "wall_climb01.png"),
             ("ClimbWall", "wall_climb02.png"), ("Sprawl", "lay02.png"),
             ("Tripping", "trip02.png")]
    new = {p[0] for p in picks[:11]}
    PAD, LBL, COLS = 12, 20, 6
    rows = (len(picks) + COLS - 1) // COLS
    W = PAD + COLS * (160 + PAD)
    H = PAD * (rows + 1) + rows * (160 + LBL)
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    for i, (name, fn) in enumerate(picks):
        x = PAD + (i % COLS) * (160 + PAD)
        y = PAD + (i // COLS) * (160 + LBL + PAD) + LBL
        sheet.paste(cell(frame("Blue", fn)), (x, y))
        tag = "new" if name in new else "re-drawn"
        d.text((x + 2, y - 16), f"{name} [{tag}]", fill=FG if name in new else ACC)
    sheet.save(os.path.join(DOCS, "new-moves.png"), optimize=True)


def action_grid():
    common = [("Idle", "idle02.png"), ("Wave", "wave03.png"), ("FightCombo", "fight_punch01.png"),
              ("SwordPractice", "sword03.png"), ("Mine", "mine02.png"), ("Sleep", "sleep02.png"),
              ("SnackTime", "snack03.png"), ("Juggle", "juggle01.png"), ("Victory", "victory03.png"),
              ("Meditate", "meditate02.png")]
    sigs = {"Orange": ("DrawAlive", "draw05.png"), "Yellow": ("Tinker", "tinker03.png"),
            "Blue": ("BrewPotion", "potion03.png"), "Green": ("PlayGuitar", "music02.png")}
    PAD, LBL = 6, 18
    cols = len(common) + 1
    W = PAD + cols * (160 + PAD)
    H = PAD + len(SPEC.CHARS) * (160 + PAD + LBL)
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    for r, ch in enumerate(SPEC.CHARS):
        y = PAD + r * (160 + PAD + LBL)
        d.text((PAD, y), f"{ch}   (last column = signature move)", fill=FG)
        for c, (name, fn) in enumerate(common + [sigs[ch]]):
            x = PAD + c * (160 + PAD)
            bg = Image.new("RGB", (160, 160), (48, 50, 58))
            f = frame(ch, fn)
            bg.paste(f, (0, 0), f)
            sheet.paste(bg, (x, y + LBL))
            d.text((x + 2, y + LBL + 2), name, fill=(150, 200, 255))
    sheet = sheet.resize((int(sheet.width * 0.8), int(sheet.height * 0.8)), Image.LANCZOS)
    sheet.save(os.path.join(DOCS, "action-grid.png"), optimize=True)


def before_after():
    """Needs the pre-change frames in /tmp/orig_pack to draw the "before" half."""
    pairs = [("Yellow", "fall01.png", "161x128 and 113px of art - the throwing arm is sliced at the right edge"),
             ("Green", "hang01.png", "128x216 - hung 211px below the ceiling anchor (2.3x everyone else)"),
             ("Blue", "lay01.png", "130x128 - art cut on BOTH sides, so lying down looked beheaded"),
             ("Orange", "wall_climb01.png", "128x152 - legs sank 16px under the anchor: feet chopped at the screen bottom")]
    before = "/tmp/orig_pack"
    if not os.path.isdir(before):
        print("docs/before-after.png skipped: pre-change frames not in /tmp/orig_pack")
        return
    S, PAD, CAP, LBL = 1.4, 16, 34, 18
    CELL = int(160 * S)
    W = PAD + len(pairs) * (CELL + PAD)
    H = PAD * 2 + LBL * 3 + CELL * 2 + CAP
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 6), "BEFORE  -  original pack art, drawn to its own canvas (red)", fill=(255, 130, 130))
    d.text((PAD, PAD + LBL + CELL + LBL + 8),
           "AFTER  -  regenerated, art 16px clear of every edge", fill=(150, 245, 170))
    for i, (ch, fn, note) in enumerate(pairs):
        x = PAD + i * (CELL + PAD)
        for row, src in ((0, os.path.join(before, ch, fn)),
                         (1, os.path.join(ROOT, "AVA Shimejis", ch, fn))):
            y = PAD + LBL + row * (CELL + PAD + LBL)
            im = Image.open(src).convert("RGBA")
            w, h = im.size
            sc = min(1.0, (CELL - 4) / max(w, h))
            nw, nh = max(1, int(w * sc)), max(1, int(h * sc))
            c = checker(w, h)
            c.paste(im, (0, 0), im)
            sheet.paste(c.resize((nw, nh), Image.NEAREST), (x, y))
            d.rectangle([x - 1, y - 1, x + nw, y + nh],
                        outline=(220, 80, 80) if row == 0 else (95, 205, 115))
            d.text((x, y + nh + 3), f"{ch}/{fn}  {w}x{h}", fill=(210, 210, 220))
        d.text((x, H - CAP), note[:46], fill=(190, 190, 200))
        if len(note) > 46:
            d.text((x, H - CAP + 13), note[46:], fill=(190, 190, 200))
    sheet.save(os.path.join(DOCS, "before-after.png"), optimize=True)


def main():
    os.makedirs(DOCS, exist_ok=True)
    hero()
    new_moves()
    action_grid()
    before_after()
    for name in sorted(os.listdir(DOCS)):
        print(f"docs/{name}")


if __name__ == "__main__":
    main()
