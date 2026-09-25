#!/usr/bin/env python3
"""Procedural Shimeji frame generator - AvA stick figures, HARD-EDGE pixel style.

Canvas 128x128, feet anchored at (64,128). Drawn at NATIVE resolution with
hard pixel edges to match the hand-drawn originals (no supersample blur).
Body color varies per character; props keep fixed colors.
"""
import math, os, sys
from PIL import Image, ImageDraw

W = H = 128

BODY = {                    # measured from original pack
    "Blue":   (37, 192, 255),
    "Orange": (242, 111, 36),
    "Yellow": (255, 197, 0),
    "Green":  (95, 183, 0),
}
LIMB_W = 6                  # limbs: arms, legs
BODY_W = 9                  # torso: wider to match stock neck/shoulder area
HEAD_R = 12                 # match stock frames exactly

P = {   # fixed prop palette (same for every character)
    "wood":   (139, 90, 43),
    "steel":  (217, 226, 236),
    "steel_d":(140, 155, 175),
    "gold":   (240, 180, 41),
    "grip":   (123, 75, 38),
    "guitar": (181, 101, 29),
    "guitar_d": (90, 45, 10),
    "hole":   (40, 20, 8),
    "red":    (233, 79, 55),
    "lead":   (50, 50, 55),
    "cream":  (232, 195, 158),
    "glass":  (191, 227, 255),
    "liquid": (57, 211, 83),
    "white":  (255, 255, 255),
    "ink":    (25, 30, 40),
    "spark":  (255, 224, 60),
    "redstone": (255, 59, 48),
    "slash":  (230, 255, 255),
    "leaf":   (46, 160, 67),
    "dust":   (200, 200, 200),
    "flash":  (255, 255, 230),
}

# ---------------------------------------------------------------- helpers (1x, hard edges)
def new_canvas():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))

def finish(im):
    return im

def _i(v):
    if isinstance(v, (tuple, list)):
        return tuple(int(round(c)) for c in v)
    return int(round(v))

def limb(d, pts, w, color):
    pts = [_i(p) for p in pts]
    d.line(pts, fill=color + (255,), width=_i(w), joint="curve")
    for p in pts:
        r = _i(w) / 2
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color + (255,))

def dot(d, pos, r, color, alpha=255):
    x, y = _i(pos); r = _i(r)
    d.ellipse([x-r, y-r, x+r, y+r], fill=color + (alpha,))

def poly(d, pts, color, alpha=255, outline=None):
    pts = [_i(p) for p in pts]
    d.polygon(pts, fill=color + (alpha,))
    if outline:
        d.line(pts + [pts[0]], fill=outline + (255,), width=1)

def seg(d, a, b, w, color, alpha=255):
    d.line([_i(a), _i(b)], fill=color + (alpha,), width=max(1, _i(w)))

def arc(d, bbox, start, end, w, color, alpha=255):
    x0, y0, x1, y1 = bbox
    d.arc([_i((x0, y0)), _i((x1, y1))], start, end, fill=color + (alpha,),
          width=max(1, _i(w)))

def ellipse(d, center, rx, ry, color, alpha=255, outline=None, ow=1):
    x, y = _i(center); rx, ry = _i(rx), _i(ry)
    box = [x-rx, y-ry, x+rx, y+ry]
    d.ellipse(box, fill=color + (alpha,))
    if outline:
        d.ellipse(box, outline=outline + (255,), width=max(1, _i(ow)))

def star_points(center, r_out, r_in, n=5, rot=-90):
    cx, cy = center
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts

def sparkle(d, pos, r, color=(255, 224, 60)):
    x, y = pos
    poly(d, [(x, y-r), (x+r*0.28, y-r*0.28), (x+r, y), (x+r*0.28, y+r*0.28),
             (x, y+r), (x-r*0.28, y+r*0.28), (x-r, y), (x-r*0.28, y-r*0.28)], color)

def burst(d, pos, r, core=(255,255,255), outer=(255,224,60)):
    poly(d, star_points(pos, r, r*0.55, n=8), outer)
    poly(d, star_points(pos, r*0.6, r*0.33, n=8), core)

def impact_flash(d, pos, r):
    """white flash circle with spark points — for impact frames"""
    x, y = pos
    # outer white glow
    dot(d, (x, y), r, P["white"], 220)
    # spark points radiating out
    for i in range(6):
        a = math.radians(i * 60)
        sx = x + (r + 3) * math.cos(a)
        sy = y + (r + 3) * math.sin(a)
        seg(d, (x + r*0.5*math.cos(a), y + r*0.5*math.sin(a)),
            (sx, sy), 2, P["flash"], 255)

def note(d, pos, s=1.0, color=(255,255,255)):
    x, y = pos
    for col, grow in ((P["ink"], 1), (color, 0)):
        ellipse(d, (x, y), 3.4*s+grow, 2.6*s+grow, col)
        seg(d, (x+3.2*s, y-0.5*s), (x+3.2*s, y-9*s), 2+grow, col)
        seg(d, (x+3.2*s, y-9*s), (x+6.5*s, y-7*s), 2+grow, col)

def zee(d, pos, s=1.0, alpha=255):
    x, y = pos
    w, h = 7*s, 8*s
    pts = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
    for col, ww in ((P["ink"], 4), ((255,255,255), 2)):
        d.line([_i(p) for p in pts], fill=col + (alpha,), width=max(1, _i(ww*s)),
               joint="miter")

# ---------------------------------------------------------------- figure
# PROPORTIONS: head bottom at H.y + HEAD_R, N just below head, SH close to N.
# Stock: head y=20-42, neck y=42-46, shoulders y=46-56, hips ~y=78-80
STAND = dict(
    H=(64, 28), N=(64, 40), SH=(64, 47),
    EL=(57, 60), HL=(55, 74), ER=(71, 60), HR=(73, 74),
    HIP=(64, 75), KL=(59, 98), FL=(53, 123), KR=(69, 98), FR=(75, 123),
)

def draw_figure(d, color, dy=0, dx=0, **j):
    g = dict(STAND); g.update(j)
    def mv(p):
        return (p[0] + dx, p[1] + dy)
    # Draw order: back leg, body, back arm, front leg, head, front arm
    # Body uses BODY_W (wider) to match stock neck/shoulder proportions
    limb(d, [mv(g["HIP"]), mv(g["KL"]), mv(g["FL"])], LIMB_W, color)
    limb(d, [mv(g["N"]), mv(g["SH"]), mv(g["HIP"])], BODY_W, color)
    limb(d, [mv(g["SH"]), mv(g["ER"]), mv(g["HR"])], LIMB_W, color)
    limb(d, [mv(g["HIP"]), mv(g["KR"]), mv(g["FR"])], LIMB_W, color)
    dot(d, mv(g["H"]), HEAD_R, color)
    limb(d, [mv(g["SH"]), mv(g["EL"]), mv(g["HL"])], LIMB_W, color)
    return {k: mv(v) for k, v in g.items()}

def figure_layer(color, dy=0, dx=0, **j):
    """figure on its own layer (for rotation fx)"""
    im = new_canvas()
    draw_figure(ImageDraw.Draw(im), color, dy=dy, dx=dx, **j)
    return im

# ---------------------------------------------------------------- props
def sword(d, hand, angle_deg):
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    px, py = -dy, dx
    hx, hy = hand
    seg(d, hand, (hx+dx*7, hy+dy*7), 4, P["grip"])
    dot(d, (hx-dx*1.5, hy-dy*1.5), 2, P["gold"])
    gx, gy = hx+dx*8, hy+dy*8
    seg(d, (gx-px*6, gy-py*6), (gx+px*6, gy+py*6), 3, P["gold"])
    bx, by = gx+dx*2, gy+dy*2
    tip = (bx+dx*28, by+dy*28)
    w = 2.6
    poly(d, [(bx-px*w, by-py*w), (tip[0]-px*w*0.4, tip[1]-py*w*0.4), tip,
             (tip[0]+px*w*0.4, tip[1]+py*w*0.4), (bx+px*w, by+py*w)], P["steel"],
         outline=P["steel_d"])

def pickaxe(d, top, bottom):
    seg(d, top, bottom, 4, P["wood"])
    ax, ay = top; bx, by = bottom
    dx, dy = bx-ax, by-ay
    L = math.hypot(dx, dy) or 1
    px, py = -dy/L, dx/L
    cx, cy = bx + dx/L*2, by + dy/L*2
    s = 14
    poly(d, [(cx-px*s, cy-py*s), (cx-px*4, cy-py*4-3), (cx+px*4, cy+py*4-3),
             (cx+px*s, cy+py*s), (cx+px*4, cy+py*4+3), (cx-px*4, cy-py*4+3)],
         P["steel"], outline=P["steel_d"])
    dot(d, (cx, cy), 3, P["steel_d"])

def guitar(d):
    body_c = (54, 88)
    ellipse(d, body_c, 12, 15, P["guitar"], outline=P["guitar_d"], ow=1)
    dot(d, body_c, 4, P["hole"])
    seg(d, (60, 78), (90, 50), 5, P["guitar_d"])
    seg(d, (60, 78), (90, 50), 2, P["cream"])
    dot(d, (90, 50), 3, P["guitar_d"])

def flask_prop(d, pos):
    x, y = pos
    poly(d, [(x-3, y-12), (x+3, y-12), (x+6, y-4), (x+6, y+6),
             (x-6, y+6), (x-6, y-4)], P["glass"], outline=P["ink"])
    poly(d, [(x-5, y-1), (x+5, y-1), (x+5, y+5), (x-5, y+5)], P["liquid"])
    seg(d, (x-2.5, y-12), (x+2.5, y-12), 2, P["grip"])

def wrench(d, hand, angle_deg):
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    hx, hy = hand
    ex, ey = hx+dx*16, hy+dy*16
    seg(d, hand, (ex, ey), 3, P["steel_d"])
    dot(d, (ex, ey), 4, P["steel_d"])
    dot(d, (ex+dx*2, ey+dy*2), 2, P["steel"])

def pencil(d, tip, angle_deg):
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    p0 = tip
    p1 = (tip[0]+dx*4, tip[1]+dy*4)
    p2 = (tip[0]+dx*17, tip[1]+dy*17)
    seg(d, p0, p1, 3, P["cream"])
    seg(d, p1, p2, 3, P["red"])
    dot(d, p0, 1, P["lead"])

def apple(d, pos, bitten=False):
    x, y = pos
    if bitten:
        d.pieslice([_i((x-5, y-5)), _i((x+5, y+5))], 30, 330, fill=P["red"] + (255,))
    else:
        dot(d, pos, 5, P["red"])
    seg(d, (x+1, y-5), (x+3, y-8), 1, P["grip"])
    ellipse(d, (x+5, y-7), 2.5, 1.5, P["leaf"])

def paper_plane(d, pos, s=1.0):
    """side-view paper dart pointing left"""
    x, y = pos
    poly(d, [(x-12*s, y), (x+8*s, y-4*s), (x+8*s, y+4*s)], P["white"],
         outline=P["steel_d"])
    seg(d, (x-12*s, y), (x+8*s, y), 1, P["steel_d"])

def dust(d, pos, r=4):
    dot(d, pos, r, P["dust"], 220)
    dot(d, (pos[0]+r, pos[1]-2), r-1, P["white"], 200)

def energy_ring(d, pos, r, phase=0):
    """energy ring with gaps"""
    for i in range(0, 360, 45):
        a0 = phase + i
        a1 = a0 + 30
        arc(d, (pos[0]-r, pos[1]-r, pos[0]+r, pos[1]+r), a0, a1, 2, P["energy"])

# ---------------------------------------------------------------- poses
def F(fx=None, **kw):
    fr = dict(kw); fr["fx"] = fx or []
    return fr

ANIMS = {}

# ---- wave ----
ANIMS["wave"] = [
    F(),
    F(EL=(78, 58), HL=(82, 44)),
    F(EL=(78, 58), HL=(74, 44)),
    F(EL=(78, 58), HL=(88, 44)),
]

# ---- cheer ----
ANIMS["cheer"] = [
    F(HIP=(64, 84), KL=(56, 104), FL=(52, 123), KR=(72, 104), FR=(76, 123),
      EL=(56, 66), HL=(54, 80), ER=(72, 66), HR=(74, 80)),
    F(dy=-8, EL=(54, 52), HL=(48, 36), ER=(74, 52), HR=(80, 36),
      KL=(56, 102), FL=(52, 120), KR=(72, 102), FR=(76, 120)),
    F(dy=-14, EL=(52, 46), HL=(42, 28), ER=(76, 46), HR=(86, 28),
      KL=(54, 100), FL=(46, 116), KR=(74, 100), FR=(82, 116)),
    F(dy=-12, EL=(52, 46), HL=(44, 30), ER=(76, 46), HR=(84, 30),
      KL=(58, 102), FL=(52, 118), KR=(70, 102), FR=(76, 118)),
    F(HIP=(64, 84), KL=(56, 104), FL=(52, 123), KR=(72, 104), FR=(76, 123),
      EL=(54, 54), HL=(48, 40), ER=(74, 54), HR=(80, 40)),
    F(),
]

# ---- sword (5 frames) ----
ANIMS["sword"] = [
    F(EL=(54, 64), HL=(50, 82), fx=[("sword", "HL", 75)]),
    F(EL=(48, 52), HL=(46, 40), fx=[("sword", "HL", -130)]),
    F(EL=(44, 56), HL=(38, 58),
      fx=[("sword", "HL", 50), ("arc", (20, 36, 80, 96), 200, 340)]),
    F(EL=(46, 62), HL=(40, 68),
      fx=[("sword", "HL", 8), ("arc", (16, 48, 84, 88), 170, 350)]),
    F(EL=(54, 64), HL=(50, 80), fx=[("sword", "HL", 60)]),
]

# ---- cursorslash (3 frames) ----
ANIMS["cursorslash"] = [
    F(HIP=(64, 86), KL=(54, 105), FL=(50, 123), KR=(74, 105), FR=(78, 123),
      EL=(52, 58), HL=(46, 46), fx=[("sword", "HL", -60)]),
    F(dy=-12, EL=(54, 44), HL=(46, 28), ER=(74, 56), HR=(80, 44),
      KL=(56, 100), FL=(48, 116), KR=(72, 100), FR=(80, 116),
      fx=[("sword", "HL", -45), ("arc", (24, -4, 104, 56), 180, 360),
          ("speed", (60, 26))]),
    F(HIP=(64, 84), KL=(56, 104), FL=(52, 123), KR=(72, 104), FR=(76, 123),
      EL=(54, 62), HL=(48, 56), fx=[("sword", "HL", 30)]),
]

# ---- fistpump: punch the sky, come back ----
ANIMS["fistpump"] = [
    F(EL=(56, 66), HL=(54, 80), ER=(72, 66), HR=(74, 80)),
    F(dy=-4, EL=(56, 58), HL=(54, 72), ER=(78, 44), HR=(82, 28),
      KL=(58, 102), FL=(52, 120), KR=(70, 102), FR=(76, 120),
      fx=[("burst", (86, 22), 8)]),
    F(dy=-6, EL=(56, 56), HL=(54, 70), ER=(78, 42), HR=(82, 26),
      KL=(58, 102), FL=(52, 120), KR=(70, 102), FR=(76, 120)),
    F(),
]

# ---- mine ----
ANIMS["mine"] = [
    F(FL=(44, 123), FR=(84, 123), KL=(52, 102), KR=(76, 102), HIP=(64, 82),
      EL=(58, 56), HL=(58, 46), ER=(68, 52), HR=(64, 42),
      fx=[("pick", (62, 42), (40, 16))]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 102), KR=(76, 102), HIP=(64, 86),
      EL=(52, 68), HL=(44, 80), ER=(60, 66), HR=(50, 76),
      fx=[("pick", (48, 76), (30, 104))]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 102), KR=(76, 102), HIP=(64, 86),
      EL=(52, 68), HL=(44, 80), ER=(60, 66), HR=(50, 76),
      fx=[("pick", (48, 76), (30, 104)), ("burst", (30, 108), 12),
          ("chips", [(36, 100), (24, 96), (40, 92)])]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 102), KR=(76, 102), HIP=(64, 84),
      EL=(56, 60), HL=(52, 62), ER=(64, 58), HR=(58, 56),
      fx=[("pick", (56, 58), (44, 36))]),
]

# ---- sleep ----
SLEEP_J = dict(H=(26, 108), N=(38, 110), SH=(48, 112), HIP=(80, 114),
               EL=(38, 120), HL=(30, 116), ER=(62, 106), HR=(72, 108),
               KL=(98, 110), FL=(114, 112), KR=(94, 120), FR=(108, 123))
ANIMS["sleep"] = [
    F(fx=[("z", (46, 84), 0.9, 255)], **SLEEP_J),
    F(fx=[("z", (46, 84), 0.9, 200), ("z", (56, 68), 1.2, 255)], **SLEEP_J),
    F(fx=[("z", (46, 84), 0.9, 150), ("z", (58, 66), 1.2, 220),
        ("z", (72, 46), 1.6, 255)], **SLEEP_J),
]

# ---- hurt (3 frames) ----
HURT_J = dict(H=(52, 70), N=(54, 82), SH=(54, 90), HIP=(64, 112),
              KL=(86, 114), FL=(106, 122), KR=(88, 107), FR=(108, 113),
              EL=(46, 100), HL=(44, 114), ER=(62, 100), HR=(64, 114))
ANIMS["hurt"] = [
    F(fx=[("impact_flash", (54, 74), 10)], **HURT_J),
    F(fx=[("impact_flash", (56, 72), 7)], **HURT_J),
    F(dx=2, HIP=(64, 82), KL=(58, 102), FL=(53, 123), KR=(70, 102), FR=(75, 123),
      EL=(56, 66), HL=(54, 80), ER=(72, 66), HR=(74, 80)),
]

# ---- glitch (3 frames) ----
ANIMS["glitch"] = [F(), F(dx=2), F(dx=-2)]

# ---- backflip (rotation) ----
ANIMS["flip"] = [
    F(cant_rotate=False, HIP=(64, 86), KL=(54, 105), FL=(50, 123), KR=(74, 105),
      FR=(78, 123), EL=(56, 66), HL=(54, 80), ER=(72, 66), HR=(74, 80)),
    F(cant_rotate=False, dy=-16, EL=(52, 48), HL=(44, 32), ER=(76, 48), HR=(84, 32),
      KL=(56, 102), FL=(50, 118), KR=(72, 102), FR=(78, 118)),
    F(flip=(60, -26)),
    F(flip=(150, -28)),
    F(flip=(245, -20)),
    F(cant_rotate=False, HIP=(64, 86), KL=(54, 105), FL=(50, 123), KR=(74, 105),
      FR=(78, 123), EL=(54, 54), HL=(48, 40), ER=(74, 54), HR=(80, 40)),
]
FLIP_BASE = dict(H=(64, 30), N=(64, 40), SH=(64, 48), HIP=(64, 80),
                 EL=(56, 58), HL=(52, 70), ER=(72, 58), HR=(76, 70),
                 KL=(56, 98), FL=(54, 114), KR=(72, 98), FR=(74, 114))

# ---- snack ----
ANIMS["snack"] = [
    F(ER=(72, 64), HR=(75, 78), fx=[("apple", (80, 82), False)]),
    F(ER=(72, 58), HR=(70, 52), fx=[("apple", (71, 44), False)]),
    F(dy=1, ER=(72, 58), HR=(70, 52),
      fx=[("apple", (71, 44), True), ("crumbs", [(62, 48), (80, 50), (70, 56)])]),
    F(ER=(72, 64), HR=(75, 78), fx=[("apple", (80, 82), True)]),
]

# ---- slide (4 frames) ----
ANIMS["slide"] = [
    F(N=(66, 42), SH=(68, 50), H=(70, 36), HIP=(66, 86),
      KL=(52, 104), FL=(44, 122), KR=(76, 102), FR=(80, 121),
      EL=(74, 64), HL=(80, 76), ER=(72, 60), HR=(78, 50),
      fx=[("speed", (90, 86))]),
    F(N=(60, 58), SH=(62, 66), H=(58, 52), HIP=(64, 96),
      KL=(42, 112), FL=(24, 121), KR=(50, 110), FR=(34, 120),
      EL=(72, 80), HL=(80, 96), ER=(70, 76), HR=(78, 90),
      fx=[("dust", (88, 114), 5), ("dust", (98, 108), 3), ("speed", (100, 76))]),
    F(N=(60, 58), SH=(62, 66), H=(58, 52), HIP=(64, 96),
      KL=(42, 112), FL=(24, 121), KR=(50, 110), FR=(34, 120),
      EL=(72, 80), HL=(80, 96), ER=(70, 76), HR=(78, 90),
      fx=[("dust", (92, 114), 6), ("speed", (100, 76))]),
    F(),
]

# ---- pushups ----
PUSH_UP = dict(SH=(52, 92), HIP=(88, 92), N=(40, 90), H=(30, 88),
               EL=(48, 104), HL=(46, 119), ER=(56, 104), HR=(54, 119),
               KL=(100, 102), FL=(112, 120), KR=(102, 102), FR=(114, 120))
PUSH_DOWN = dict(SH=(52, 100), HIP=(88, 98), N=(40, 99), H=(30, 97),
                 EL=(38, 106), HL=(46, 119), ER=(62, 106), HR=(54, 119),
                 KL=(100, 106), FL=(112, 120), KR=(102, 106), FR=(114, 120))
ANIMS["pushup"] = [F(**PUSH_UP), F(**PUSH_DOWN), F(**PUSH_UP), F(**PUSH_DOWN)]

# ---- sneeze ----
ANIMS["sneeze"] = [
    F(H=(66, 24), N=(65, 36), SH=(64, 47), EL=(54, 60), HL=(50, 74),
      ER=(74, 60), HR=(78, 74)),
    F(H=(58, 30), N=(60, 42), SH=(62, 52), EL=(54, 64), HL=(50, 76),
      ER=(70, 64), HR=(68, 76), fx=[("achoo", (44, 32))]),
    F(),
]

# ---- paper plane ----
ANIMS["plane"] = [
    F(ER=(74, 56), HR=(80, 44), fx=[("plane_at", (80, 40))]),
    F(ER=(70, 60), HR=(52, 58), EL=(58, 62), HL=(56, 76),
      fx=[("plane_at", (28, 48)), ("speed", (44, 48))]),
    F(fx=[("plane_at", (10, 42))]),
    F(),
]

# ---- signatures ----
STAR_C = (90, 60)
ANIMS["draw"] = [
    F(ER=(72, 60), HR=(80, 62), fx=[("pencil", STAR_C, 20), ("starpath", 0.3, False)]),
    F(ER=(72, 60), HR=(82, 60), fx=[("pencil", STAR_C, 0), ("starpath", 0.55, False)]),
    F(ER=(72, 60), HR=(80, 64), fx=[("pencil", STAR_C, -20), ("starpath", 0.8, False)]),
    F(ER=(72, 60), HR=(82, 62), fx=[("pencil", STAR_C, 10), ("starpath", 1.0, False)]),
    F(ER=(72, 58), HR=(84, 56), fx=[("starpath", 1.0, True),
        ("sparkles", [(78, 48), (102, 52), (90, 76)], 5)]),
    F(ER=(74, 54), HR=(86, 48), fx=[("starpath", 1.0, True),
        ("sparkles", [(76, 46), (104, 50), (90, 78), (90, 40)], 7)]),
]

ANIMS["tinker"] = [
    F(HIP=(64, 92), KL=(56, 106), FL=(50, 123), KR=(72, 112), FR=(82, 123),
      SH=(64, 58), N=(64, 46), H=(64, 34), ER=(70, 70), HR=(76, 84),
      fx=[("wrench", "HR", 40)]),
    F(HIP=(64, 92), KL=(56, 106), FL=(50, 123), KR=(72, 112), FR=(82, 123),
      SH=(64, 58), N=(64, 46), H=(64, 34), ER=(70, 70), HR=(78, 82),
      fx=[("wrench", "HR", 55), ("redstone", 0)]),
    F(HIP=(64, 92), KL=(56, 106), FL=(50, 123), KR=(72, 112), FR=(82, 123),
      SH=(64, 58), N=(64, 46), H=(64, 34), ER=(70, 70), HR=(76, 84),
      fx=[("wrench", "HR", 40), ("burst", (84, 92), 10)]),
    F(HIP=(64, 92), KL=(56, 106), FL=(50, 123), KR=(72, 112), FR=(82, 123),
      SH=(64, 58), N=(64, 46), H=(64, 34), ER=(70, 70), HR=(78, 82),
      fx=[("wrench", "HR", 55), ("redstone", 1)]),
]

ANIMS["potion"] = [
    F(ER=(72, 64), HR=(74, 72), fx=[("flask", "HR")]),
    F(ER=(74, 60), HR=(78, 62), fx=[("flask", "HR"), ("bubbles", 0)]),
    F(ER=(76, 54), HR=(82, 50), fx=[("flask", "HR"), ("bubbles", 1)]),
    F(ER=(76, 54), HR=(82, 50), fx=[("flask", "HR"), ("bubbles", 1),
                                    ("sparkles", [(72, 36), (94, 40)], 5)]),
]

ANIMS["music"] = [
    F(EL=(66, 62), HL=(78, 56), ER=(62, 72), HR=(54, 82), fx=[("guitar",), ("notes", 0)]),
    F(EL=(66, 62), HL=(78, 56), ER=(62, 72), HR=(58, 84), fx=[("guitar",), ("notes", 0)]),
    F(EL=(68, 60), HL=(82, 54), ER=(62, 72), HR=(54, 82), fx=[("guitar",), ("notes", 1)]),
    F(EL=(68, 60), HL=(82, 54), ER=(62, 72), HR=(58, 84), fx=[("guitar",), ("notes", 1)]),
]

# ====================================================================
#   NEW ANIMATIONS — clean poses, short neck, crisp motion
# ====================================================================

# ---- walljump: approach, crouch, leap, airborne, land ----
ANIMS["walljump"] = [
    F(HIP=(72, 80), KL=(78, 98), FL=(84, 118), KR=(80, 102), FR=(86, 122),
      EL=(56, 62), HL=(50, 74), ER=(64, 58), HR=(58, 50),
      N=(68, 42), SH=(68, 49), H=(72, 30)),
    F(HIP=(70, 90), KL=(76, 106), FL=(82, 123), KR=(78, 108), FR=(84, 123),
      EL=(50, 72), HL=(44, 84), ER=(60, 68), HR=(54, 62),
      N=(66, 48), SH=(66, 55), H=(68, 36)),
    F(dy=-20, dx=-8, HIP=(64, 78), KL=(56, 98), FL=(48, 118), KR=(72, 98), FR=(80, 118),
      EL=(50, 52), HL=(40, 40), ER=(76, 48), HR=(86, 36),
      N=(60, 36), SH=(60, 43), H=(56, 24), fx=[("speed", (36, 66))]),
    F(dy=-12, HIP=(64, 80), KL=(54, 100), FL=(48, 120), KR=(74, 100), FR=(82, 120),
      EL=(54, 54), HL=(46, 42), ER=(72, 54), HR=(80, 44),
      N=(62, 38), SH=(62, 45), H=(60, 26)),
    F(dy=-4, HIP=(64, 84), KL=(56, 102), FL=(52, 123), KR=(72, 102), FR=(78, 123),
      EL=(56, 62), HL=(52, 76), ER=(72, 62), HR=(76, 76),
      fx=[("dust", (54, 120), 4), ("dust", (74, 118), 3)]),
]

# ---- yawn: big stretch ----
ANIMS["yawn"] = [
    F(H=(68, 24), N=(66, 36), SH=(64, 47),
      EL=(56, 60), HL=(54, 74), ER=(72, 60), HR=(74, 74)),
    F(H=(68, 20), N=(66, 32), SH=(64, 44),
      EL=(48, 40), HL=(42, 24), ER=(80, 40), HR=(86, 24),
      KL=(58, 102), FL=(52, 123), KR=(70, 102), FR=(76, 123)),
    F(H=(68, 22), N=(66, 34), SH=(64, 46),
      EL=(50, 44), HL=(44, 30), ER=(78, 44), HR=(84, 30),
      KL=(58, 102), FL=(52, 123), KR=(70, 102), FR=(76, 123)),
    F(),
]

# ---- headscratch: hand up to head ----
ANIMS["headscratch"] = [
    F(EL=(72, 44), HL=(68, 28), ER=(70, 62), HR=(74, 76)),
    F(EL=(74, 42), HL=(72, 26), ER=(70, 62), HR=(74, 76)),
    F(EL=(70, 44), HL=(66, 28), ER=(70, 62), HR=(74, 76)),
    F(EL=(72, 42), HL=(70, 26), ER=(70, 62), HR=(74, 76)),
]

# ---- think: hand to chin ----
ANIMS["think"] = [
    F(EL=(60, 62), HL=(64, 74), ER=(72, 58), HR=(74, 72)),
    F(EL=(68, 54), HL=(72, 42), ER=(72, 58), HR=(74, 72)),
    F(EL=(70, 52), HL=(74, 38), ER=(72, 58), HR=(74, 72),
      H=(68, 26), N=(66, 36)),
    F(EL=(68, 54), HL=(72, 42), ER=(72, 58), HR=(74, 72)),
]

# ---- faint: wobble, tip, land flat ----
ANIMS["faint"] = [
    F(HIP=(64, 82), EL=(56, 64), HL=(54, 78), ER=(72, 64), HR=(74, 78),
      KL=(58, 102), FL=(52, 123), KR=(70, 102), FR=(76, 123)),
    F(N=(60, 42), SH=(60, 52), H=(56, 30), HIP=(64, 86),
      EL=(52, 66), HL=(46, 78), ER=(68, 66), HR=(66, 78),
      KL=(60, 106), FL=(56, 123), KR=(68, 106), FR=(72, 123)),
    F(HIP=(68, 98), N=(64, 100), SH=(60, 102), H=(52, 98),
      EL=(48, 110), HL=(40, 118), ER=(72, 106), HR=(80, 112),
      KL=(84, 110), FL=(100, 118), KR=(90, 106), FR=(106, 114)),
    F(HIP=(70, 110), N=(58, 112), SH=(52, 114), H=(42, 110),
      EL=(40, 118), HL=(32, 123), ER=(66, 114), HR=(76, 118),
      KL=(92, 114), FL=(110, 120), KR=(96, 112), FR=(112, 118)),
    F(HIP=(70, 110), N=(58, 112), SH=(52, 114), H=(42, 110),
      EL=(40, 118), HL=(32, 123), ER=(66, 114), HR=(76, 118),
      KL=(92, 114), FL=(110, 120), KR=(96, 112), FR=(112, 118),
      fx=[("impact_flash", (56, 106), 6)]),
]

# ---- sneak: low crouch, slow steps ----
ANIMS["sneak"] = [
    F(HIP=(64, 90), N=(62, 44), SH=(62, 52), H=(60, 32),
      KL=(56, 108), FL=(52, 123), KR=(72, 108), FR=(78, 123),
      EL=(54, 68), HL=(50, 80), ER=(70, 68), HR=(74, 80)),
    F(HIP=(66, 90), N=(64, 44), SH=(64, 52), H=(62, 32),
      KL=(58, 108), FL=(56, 123), KR=(74, 108), FR=(80, 123),
      EL=(56, 68), HL=(52, 80), ER=(72, 68), HR=(76, 80)),
    F(HIP=(64, 90), N=(62, 44), SH=(62, 52), H=(60, 32),
      KL=(56, 108), FL=(52, 123), KR=(72, 108), FR=(78, 123),
      EL=(54, 68), HL=(50, 80), ER=(70, 68), HR=(74, 80)),
    F(HIP=(62, 90), N=(60, 44), SH=(60, 52), H=(58, 32),
      KL=(54, 108), FL=(50, 123), KR=(70, 108), FR=(76, 123),
      EL=(52, 68), HL=(48, 80), ER=(68, 68), HR=(72, 80)),
]

# ---- shrug: arms up then down ----
ANIMS["shrug"] = [
    F(EL=(56, 62), HL=(54, 76), ER=(72, 62), HR=(74, 76)),
    F(EL=(50, 52), HL=(42, 44), ER=(78, 52), HR=(86, 44)),
    F(EL=(50, 52), HL=(42, 44), ER=(78, 52), HR=(86, 44)),
    F(EL=(56, 62), HL=(54, 76), ER=(72, 62), HR=(74, 76)),
]

# ---- jump: crouch, launch, apex, descend, land ----
ANIMS["jump"] = [
    F(HIP=(64, 90), KL=(52, 106), FL=(48, 123), KR=(76, 106), FR=(80, 123),
      EL=(56, 66), HL=(54, 80), ER=(72, 66), HR=(74, 80)),
    F(dy=-6, HIP=(64, 82), KL=(54, 100), FL=(50, 123), KR=(74, 100), FR=(78, 123),
      EL=(50, 54), HL=(44, 42), ER=(78, 54), HR=(84, 42)),
    F(dy=-22, HIP=(64, 76), KL=(58, 96), FL=(54, 116), KR=(70, 96), FR=(74, 116),
      EL=(48, 50), HL=(40, 38), ER=(80, 50), HR=(88, 38)),
    F(dy=-8, HIP=(64, 82), KL=(56, 102), FL=(52, 122), KR=(72, 102), FR=(76, 122),
      EL=(54, 58), HL=(48, 48), ER=(74, 58), HR=(80, 48)),
    F(dy=-2, HIP=(64, 86), KL=(56, 104), FL=(52, 123), KR=(72, 104), FR=(76, 123),
      EL=(56, 64), HL=(54, 78), ER=(72, 64), HR=(74, 78),
      fx=[("dust", (54, 120), 4), ("dust", (74, 120), 3)]),
]

# ---- facepalm: hand to face, hold ----
ANIMS["facepalm"] = [
    F(EL=(56, 62), HL=(54, 76), ER=(72, 62), HR=(74, 76)),
    F(EL=(62, 46), HL=(60, 34), ER=(72, 62), HR=(74, 76)),
    F(EL=(64, 44), HL=(62, 32), ER=(72, 62), HR=(74, 76),
      N=(62, 38), H=(60, 26)),
    F(EL=(64, 44), HL=(62, 32), ER=(72, 62), HR=(74, 76),
      N=(62, 38), H=(60, 26)),
]

# ---- dab ----
ANIMS["dab"] = [
    F(EL=(56, 62), HL=(54, 76), ER=(72, 62), HR=(74, 76)),
    F(N=(58, 42), SH=(60, 52), H=(52, 32),
      EL=(52, 48), HL=(46, 36), ER=(68, 56), HR=(56, 46),
      KL=(58, 102), FL=(52, 123), KR=(70, 102), FR=(76, 123)),
    F(N=(56, 44), SH=(58, 54), H=(48, 34),
      EL=(50, 46), HL=(42, 34), ER=(66, 54), HR=(52, 44),
      KL=(58, 102), FL=(52, 123), KR=(70, 102), FR=(76, 123),
      fx=[("speed", (36, 44))]),
    F(N=(58, 42), SH=(60, 52), H=(52, 32),
      EL=(52, 48), HL=(46, 36), ER=(68, 56), HR=(56, 46),
      KL=(58, 102), FL=(52, 123), KR=(70, 102), FR=(76, 123)),
]

# ---- balance: arms out, sway ----
ANIMS["balance"] = [
    F(HIP=(64, 82), KL=(60, 102), FL=(58, 123), KR=(68, 102), FR=(70, 123),
      EL=(44, 58), HL=(30, 56), ER=(84, 58), HR=(98, 56)),
    F(HIP=(62, 82), KL=(56, 102), FL=(52, 123), KR=(68, 102), FR=(72, 123),
      N=(60, 38), SH=(60, 47), H=(56, 26),
      EL=(42, 56), HL=(26, 54), ER=(82, 60), HR=(96, 58)),
    F(HIP=(64, 82), KL=(60, 102), FL=(58, 123), KR=(68, 102), FR=(70, 123),
      EL=(44, 58), HL=(30, 56), ER=(84, 58), HR=(98, 56)),
    F(HIP=(66, 82), KL=(60, 102), FL=(56, 123), KR=(72, 102), FR=(76, 123),
      N=(68, 38), SH=(68, 47), H=(72, 26),
      EL=(46, 60), HL=(32, 58), ER=(86, 56), HR=(100, 54)),
    F(HIP=(64, 82), KL=(60, 102), FL=(58, 123), KR=(68, 102), FR=(70, 123),
      EL=(44, 58), HL=(30, 56), ER=(84, 58), HR=(98, 56)),
]

# ---- hover: gentle bob ----
ANIMS["hover"] = [
    F(dy=-4, EL=(54, 54), HL=(48, 44), ER=(74, 54), HR=(80, 44),
      KL=(58, 98), FL=(52, 118), KR=(70, 98), FR=(76, 118)),
    F(dy=-8, EL=(52, 52), HL=(46, 40), ER=(76, 52), HR=(82, 40),
      KL=(58, 96), FL=(50, 116), KR=(70, 96), FR=(76, 116)),
    F(dy=-6, EL=(54, 54), HL=(48, 42), ER=(74, 54), HR=(80, 42),
      KL=(58, 98), FL=(52, 118), KR=(70, 98), FR=(76, 118)),
    F(dy=-4, EL=(54, 54), HL=(48, 44), ER=(74, 54), HR=(80, 44),
      KL=(58, 98), FL=(52, 118), KR=(70, 98), FR=(76, 118)),
]

# ---- panicspin: alarm, spin, dizzy ----
ANIMS["panicspin"] = [
    F(EL=(52, 58), HL=(46, 48), ER=(76, 58), HR=(82, 48)),
    F(EL=(78, 58), HL=(84, 48), ER=(54, 58), HR=(48, 48),
      N=(66, 40), SH=(66, 47), H=(68, 28)),
    F(EL=(52, 58), HL=(46, 48), ER=(76, 58), HR=(82, 48)),
    F(EL=(78, 58), HL=(84, 48), ER=(54, 58), HR=(48, 48),
      N=(62, 40), SH=(62, 47), H=(60, 28)),
    F(EL=(56, 62), HL=(52, 74), ER=(72, 62), HR=(76, 74),
      fx=[("impact_flash", (64, 28), 6)]),
    F(),
]

# ---- celebrate: jump + V arms ----
ANIMS["celebrate"] = [
    F(HIP=(64, 90), KL=(52, 106), FL=(48, 123), KR=(76, 106), FR=(80, 123),
      EL=(54, 68), HL=(50, 80), ER=(74, 68), HR=(78, 80)),
    F(dy=-12, HIP=(64, 78), KL=(54, 98), FL=(50, 118), KR=(74, 98), FR=(78, 118),
      EL=(52, 50), HL=(46, 36), ER=(76, 50), HR=(82, 36)),
    F(dy=-10, EL=(46, 46), HL=(32, 38), ER=(82, 46), HR=(96, 38),
      KL=(56, 100), FL=(50, 118), KR=(72, 100), FR=(78, 118),
      fx=[("impact_flash", (64, 30), 10)]),
    F(dy=-4, EL=(54, 54), HL=(46, 42), ER=(74, 54), HR=(82, 42),
      KL=(58, 102), FL=(52, 120), KR=(70, 102), FR=(76, 120)),
    F(EL=(56, 62), HL=(54, 76), ER=(72, 62), HR=(74, 76),
      fx=[("dust", (54, 120), 3), ("dust", (74, 120), 3)]),
]

# ---- dash: aggressive sprint with speed lines ----
ANIMS["dash"] = [
    F(N=(68, 42), SH=(70, 49), H=(72, 30), HIP=(66, 80),
      KL=(54, 98), FL=(46, 120), KR=(76, 98), FR=(84, 118),
      EL=(60, 58), HL=(54, 48), ER=(78, 56), HR=(84, 46),
      fx=[("speed", (38, 76))]),
    F(N=(68, 40), SH=(70, 47), H=(74, 28), HIP=(66, 78),
      KL=(50, 96), FL=(38, 116), KR=(74, 98), FR=(82, 118),
      EL=(62, 56), HL=(58, 44), ER=(80, 54), HR=(88, 42),
      fx=[("speed", (34, 72))]),
    F(N=(68, 42), SH=(70, 49), H=(72, 30), HIP=(66, 80),
      KL=(56, 98), FL=(48, 120), KR=(78, 98), FR=(86, 118),
      EL=(60, 58), HL=(54, 48), ER=(78, 56), HR=(84, 46),
      fx=[("speed", (40, 78))]),
    F(N=(68, 40), SH=(70, 47), H=(74, 28), HIP=(66, 78),
      KL=(52, 96), FL=(42, 116), KR=(76, 98), FR=(84, 118),
      EL=(62, 56), HL=(58, 44), ER=(80, 54), HR=(88, 42),
      fx=[("speed", (36, 74))]),
    F(N=(68, 42), SH=(70, 49), H=(72, 30), HIP=(66, 80),
      KL=(54, 98), FL=(46, 120), KR=(76, 98), FR=(84, 118),
      EL=(60, 58), HL=(54, 48), ER=(78, 56), HR=(84, 46),
      fx=[("speed", (38, 76))]),
    F(N=(68, 40), SH=(70, 47), H=(74, 28), HIP=(66, 78),
      KL=(50, 96), FL=(38, 116), KR=(74, 98), FR=(82, 118),
      EL=(62, 56), HL=(58, 44), ER=(80, 54), HR=(88, 42),
      fx=[("speed", (34, 72))]),
]

COMMON = [
    # Core movement
    "wave", "cheer", "jump", "sneak", "hover", "walljump",
    # Combat (sword + slash only — fight_* removed, they looked stiff)
    "sword", "cursorslash", "fistpump", "celebrate",
    # Chill
    "sleep", "sneeze", "yawn", "headscratch", "think", "shrug", "facepalm",
    # Show-off
    "flip", "balance", "dab",
    # Action
    "mine", "snack", "plane", "slide", "pushup",
    # Dramatic
    "hurt", "faint", "panicspin", "glitch",
    # Special
    "dash",
]
SIG = {"Orange": ["draw"], "Yellow": ["tinker"], "Blue": ["potion"], "Green": ["music"]}

# ---------------------------------------------------------------- fx render
def render_fx(d, fxlist, joints):
    for fx in fxlist:
        k = fx[0]
        if k == "sword":
            _, hand, ang = fx
            sword(d, joints[hand], ang)
        elif k == "pick":
            _, top, bot = fx
            pickaxe(d, top, bot)
        elif k == "arc":
            _, bbox, a0, a1 = fx
            arc(d, bbox, a0, a1, 7, P["slash"])
            arc(d, bbox, a0, a1, 3, P["white"])
        elif k == "burst":
            _, pos, r = fx
            burst(d, pos, r)
        elif k == "chips":
            for c in fx[1]:
                dot(d, c, 2, P["steel_d"])
        elif k == "speed":
            _, (x, y) = fx
            for off in (-6, 0, 6):
                seg(d, (x - 14, y + off), (x - 4, y + off), 2, P["white"])
        elif k == "z":
            _, pos, s, a = fx
            zee(d, pos, s, a)
        elif k == "pencil":
            _, tip, ang = fx
            pencil(d, tip, ang)
        elif k == "starpath":
            _, prog, filled = fx
            pts = star_points(STAR_C, 11, 4.6)
            if filled:
                poly(d, pts, P["spark"], outline=P["ink"])
            else:
                n = max(2, int(len(pts) * prog))
                d.line([_i(p) for p in pts[:n]], fill=(255, 240, 170, 255), width=2)
        elif k == "sparkles":
            for s in fx[1]:
                sparkle(d, s, fx[2])
        elif k == "wrench":
            _, hand, ang = fx
            wrench(d, joints[hand], ang)
        elif k == "redstone":
            ph = fx[1]
            base = [(88, 96), (94, 90), (82, 88), (90, 102)] if ph == 0 else \
                   [(90, 94), (96, 98), (84, 92), (92, 86)]
            for b in base:
                dot(d, b, 2, P["redstone"])
            sparkle(d, base[0], 4)
        elif k == "flask":
            flask_prop(d, (joints[fx[1]][0] + 2, joints[fx[1]][1] - 10))
        elif k == "bubbles":
            ph = fx[1]
            hx, hy = joints["HR"]
            bub = [(hx - 2, hy - 26), (hx + 4, hy - 32)] if ph == 0 else \
                  [(hx - 3, hy - 32), (hx + 3, hy - 40), (hx, hy - 26)]
            for b in bub:
                dot(d, b, 2, P["white"])
        elif k == "guitar":
            guitar(d)
        elif k == "notes":
            ph = fx[1]
            if ph == 0:
                note(d, (96, 40), 1.0); note(d, (106, 54), 0.8)
            else:
                note(d, (100, 34), 0.9); note(d, (110, 48), 1.0)
        elif k == "apple":
            _, pos, bitten = fx
            apple(d, pos, bitten)
        elif k == "crumbs":
            for c in fx[1]:
                dot(d, c, 1, P["red"])
        elif k == "dust":
            _, pos, r = fx
            dust(d, pos, r)
        elif k == "achoo":
            _, (x, y) = fx
            for off in (-5, 0, 5):
                seg(d, (x - 4, y + off), (x - 12, y + off * 2), 2, P["white"])
            dot(d, (x - 14, y - 8), 1, P["white"])
            dot(d, (x - 16, y + 6), 1, P["white"])
        elif k == "plane_at":
            paper_plane(d, fx[1])
        elif k == "impact_flash":
            _, pos, r = fx
            impact_flash(d, pos, r)

def glitch_post(im, seed):
    """thin slice displacement + a few transparent chips (flickers per frame)"""
    im = im.copy()
    W4, H4 = im.size
    import random as _r
    rnd = _r.Random(seed)
    for _ in range(3):
        y0 = rnd.randrange(20, H4 - 30)
        h = rnd.randrange(2, 5)
        off = rnd.choice([-6, -4, 4, 6])
        band = im.crop((0, y0, W4, y0 + h))
        im.paste(band, (off, y0))
    d = ImageDraw.Draw(im)
    for _ in range(3):  # transparent chips
        x0 = rnd.randrange(40, 90); y0 = rnd.randrange(25, 115)
        d.rectangle([x0, y0, x0 + rnd.randrange(2, 5), y0 + 1], fill=(0, 0, 0, 0))
    return im

def render_frame(color_rgb, anim, frame_idx):
    fr = dict(ANIMS[anim][frame_idx])
    fx = fr.pop("fx")
    if "flip" in fr:  # rotation special-case
        angle, dy = fr["flip"]
        base = figure_layer(color_rgb, **FLIP_BASE)
        rot = base.rotate(angle, resample=Image.NEAREST, center=(64, 78))
        im = new_canvas()
        im.alpha_composite(rot, (0, dy))
        return finish(im)
    fr.pop("cant_rotate", None)
    dy = fr.pop("dy", 0); dx = fr.pop("dx", 0)
    im = new_canvas()
    d = ImageDraw.Draw(im)
    pre = [f for f in fx if f[0] == "guitar"]
    post = [f for f in fx if f[0] != "guitar"]
    joints = draw_figure(d, color_rgb, dy=dy, dx=dx, **fr)
    if pre:
        render_fx(d, pre, joints)
        g = dict(STAND); g.update(fr)
        mv = lambda p: (p[0] + dx, p[1] + dy)
        limb(d, [mv(g["SH"]), mv(g["EL"]), mv(g["HL"])], LIMB_W, color_rgb)
    render_fx(d, post, joints)
    if anim == "glitch":
        im = glitch_post(im, 11 + frame_idx * 5)
    return finish(im)

# ---------------------------------------------------------------- main
def main(out_root="AVA Shimejis", only=None, preview_dir="preview/new"):
    os.makedirs(preview_dir, exist_ok=True)
    anims_done = {}
    for char, rgb in BODY.items():
        if only and char not in only:
            continue
        names = COMMON + SIG[char]
        for anim in names:
            frames = []
            for i in range(len(ANIMS[anim])):
                img = render_frame(rgb, anim, i)
                fn = f"{anim}{i+1:02d}.png"
                img.save(os.path.join(out_root, char, fn))
                frames.append(img)
            anims_done.setdefault(anim, {})[char] = frames
    for anim, chars in anims_done.items():
        for char, frames in chars.items():
            sheet = Image.new("RGBA", (128 * len(frames), 128), (40, 40, 40, 255))
            for i, f in enumerate(frames):
                sheet.paste(f, (i * 128, 0), f)
            sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
            sheet.save(os.path.join(preview_dir, f"{anim}_{char}.png"))
    # proof sheet: originals vs new, side by side
    if (not only) or ("Blue" in only):
        import glob
        comp = []
        for f in ["AVA Shimejis/Blue/stand01.png", "AVA Shimejis/Blue/walk01.png",
                  "AVA Shimejis/Blue/run01.png",
                  "AVA Shimejis/Blue/wave02.png", "AVA Shimejis/Blue/sword03.png",
                  "AVA Shimejis/Blue/sleep03.png", "AVA Shimejis/Blue/flip03.png",
                  "AVA Shimejis/Blue/slide02.png"]:
            comp.append(Image.open(f).convert("RGBA"))
        sheet = Image.new("RGBA", (128 * len(comp), 128), (40, 40, 40, 255))
        for i, f in enumerate(comp):
            sheet.paste(f, (i * 128, 0), f)
        sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
        sheet.save(os.path.join(preview_dir, "_matchproof_Blue.png"))
    print("done. anims:", sorted(anims_done))

if __name__ == "__main__":
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    main(only=only)