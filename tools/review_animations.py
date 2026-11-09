#!/usr/bin/env python3
"""Render a pose-bearing animation audit from the shipped XML + PNGs.

Outputs ignored GIFs/strips under preview/review/ and committed contact-sheet
pages plus docs/animation-audit.md. This is a review aid, not a host simulator:
it aligns ImageAnchors and plays XML pose durations, but does not evaluate JS
conditions or window physics. The native ShimeLinux harness covers playback
coordination separately.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ava_common as SPEC

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "AVA Shimejis"
NS = {"m": "http://www.group-finity.com/Mascot"}
CHARS = SPEC.CHARS
BG = (26, 28, 34)
FG = (235, 238, 245)


def font(size=14):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def actions_with_poses(char):
    root = ET.parse(PACK / char / "conf/actions.xml").getroot()
    out = {}
    for action in root.findall(".//m:Action", NS):
        name = action.get("Name")
        poses = action.findall(".//m:Pose", NS)
        if name and poses:
            out[name] = (action, poses)
    return out


def load_pose(char, pose):
    path = PACK / char / pose.get("Image", "").lstrip("/")
    im = Image.open(path).convert("RGBA")
    anchor = tuple(int(v) for v in pose.get("ImageAnchor", "64,128").split(","))
    return im, anchor


def aligned_frame(char, pose, canvas=(160, 160), anchor_point=(80, 144)):
    im, anchor = load_pose(char, pose)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    out.alpha_composite(im, (anchor_point[0] - anchor[0], anchor_point[1] - anchor[1]))
    return out


def make_gif(char, name, poses, dest):
    frames = [aligned_frame(char, p) for p in poses]
    durations = [max(40, int(p.get("Duration", "1")) * 40) for p in poses]
    rgb = []
    for frame in frames:
        bg = Image.new("RGBA", frame.size, BG + (255,))
        bg.alpha_composite(frame)
        rgb.append(bg.convert("P", palette=Image.Palette.ADAPTIVE))
    rgb[0].save(dest, save_all=True, append_images=rgb[1:], duration=durations,
                loop=0, disposal=2)


def thumbnail(char, poses):
    pick = poses[len(poses) // 2]
    im = aligned_frame(char, pick)
    bg = Image.new("RGBA", im.size, BG + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((112, 112), Image.LANCZOS)


def verdict(name, char, poses):
    if name in SPEC.ACTIONS:
        return "KEEP", "generated reference rig; margins/continuity checked"
    if name == "WaitIdle":
        return "KEEP", "single zero-velocity pose for native waiting idle"
    # Legacy stock art is retained for host/menu compatibility, not autonomy.
    tight = []
    for pose in poses:
        path = PACK / char / pose.get("Image", "").lstrip("/")
        with Image.open(path) as im:
            box = im.convert("RGBA").getbbox()
            w, h = im.size
        if box and (box[0] <= 1 or box[1] <= 1 or box[2] >= w - 1 or box[3] >= h - 1):
            tight.append(path.name)
    if tight:
        return "REPAIR", "legacy stock art touches canvas edge: " + ", ".join(sorted(set(tight))[:3])
    return "KEEP", "legacy stock/menu compatibility; excluded from autonomous reference pool"


def main():
    preview = ROOT / "preview/review"
    preview.mkdir(parents=True, exist_ok=True)
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    all_actions = {}
    for char in CHARS:
        for name, value in actions_with_poses(char).items():
            all_actions.setdefault(name, (char, value))
    rows = []
    thumbs = []
    for name in sorted(all_actions):
        char, (action, poses) = all_actions[name]
        make_gif(char, name, poses, preview / f"{name}.gif")
        status, note = verdict(name, char, poses)
        rows.append((name, char, action.get("Type"), len(poses), status, note))
        thumbs.append((name, status, thumbnail(char, poses)))
    # Contact-sheet pages: 5 columns x 6 rows.
    cols, rows_per_page = 5, 6
    cell_w, cell_h = 150, 150
    pad = 12
    pages = math.ceil(len(thumbs) / (cols * rows_per_page))
    f = font(13)
    for page in range(pages):
        chunk = thumbs[page * cols * rows_per_page:(page + 1) * cols * rows_per_page]
        w = pad + cols * (cell_w + pad)
        h = pad + rows_per_page * (cell_h + pad)
        sheet = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(sheet)
        for i, (name, status, thumb) in enumerate(chunk):
            x = pad + (i % cols) * (cell_w + pad)
            y = pad + (i // cols) * (cell_h + pad)
            sheet.paste(thumb, (x + 19, y + 24))
            color = (140, 230, 160) if status == "KEEP" else (255, 190, 90)
            d.text((x + 4, y + 4), name[:22], fill=FG, font=f)
            d.text((x + 4, y + 132), status, fill=color, font=f)
        sheet.save(docs / f"animation-review-{page + 1}.png", optimize=True)
    # Markdown audit.
    lines = ["# Animation audit", "",
             "Generated from the shipped XML/PNGs by `tools/review_animations.py`.",
             "GIF previews are written to ignored `preview/review/`; contact sheets are",
             "`docs/animation-review-*.png`. This audit aligns anchors and plays pose",
             "durations; it is not a substitute for the native host playback harness.", "",
             f"Pose-bearing named actions reviewed: **{len(rows)}**.", "",
             "| Action | Sample character | Type | Poses | Verdict | Note |",
             "|---|---|---:|---:|---|---|"]
    for name, char, typ, count, status, note in rows:
        lines.append(f"| {name} | {char} | {typ} | {count} | {status} | {note} |")
    lines += ["", "## Policy", "",
              "- Generated reference actions are the autonomous repertoire and use hollow heads.",
              "- Legacy stock actions remain for required host interactions/menu compatibility;",
              "  they are not selected autonomously except required Fall/Dragged/Thrown/ChaseMouse paths.",
              "- `REPAIR` flags edge-tight legacy art that should be redrawn before broader reuse.", ""]
    (docs / "animation-audit.md").write_text("\n".join(lines))
    print(f"reviewed {len(rows)} pose-bearing actions; {pages} contact sheet pages")
    counts = {}
    for row in rows:
        counts[row[4]] = counts.get(row[4], 0) + 1
    print(counts)


if __name__ == "__main__":
    main()
