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
LIMB_W = 6                  # uniform stick thickness (measured: 6px core)
HEAD_R = 12

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
STAND = dict(
    H=(64, 29), N=(64, 40), SH=(64, 52),
    EL=(57, 67), HL=(55, 81), ER=(71, 67), HR=(73, 81),
    HIP=(64, 80), KL=(59, 102), FL=(53, 123), KR=(69, 102), FR=(75, 123),
)

def draw_figure(d, color, dy=0, dx=0, **j):
    g = dict(STAND); g.update(j)
    def mv(p):
        return (p[0] + dx, p[1] + dy)
    limb(d, [mv(g["SH"]), mv(g["ER"]), mv(g["HR"])], LIMB_W, color)
    limb(d, [mv(g["HIP"]), mv(g["KR"]), mv(g["FR"])], LIMB_W, color)
    limb(d, [mv(g["N"]), mv(g["SH"]), mv(g["HIP"])], LIMB_W, color)
    limb(d, [mv(g["HIP"]), mv(g["KL"]), mv(g["FL"])], LIMB_W, color)
    dot(d, mv(g["H"]), HEAD_R, color)
    limb(d, [mv(g["SH"]), mv(g["EL"]), mv(g["HL"])], LIMB_W, color)
    return {k: mv(v) for k, v in g.items()}

def figure_layer(color, dy=0, dx=0, **j):
    "figure on its own layer (for rotation fx)"
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
    # open-end wrench head: ring with wedge gap
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
    "side-view paper dart pointing left"
    x, y = pos
    poly(d, [(x-12*s, y), (x+8*s, y-4*s), (x+8*s, y+4*s)], P["white"],
         outline=P["steel_d"])
    seg(d, (x-12*s, y), (x+8*s, y), 1, P["steel_d"])

def dust(d, pos, r=4):
    dot(d, pos, r, P["dust"], 220)
    dot(d, (pos[0]+r, pos[1]-2), r-1, P["white"], 200)

# ---------------------------------------------------------------- poses
def F(fx=None, **kw):
    fr = dict(kw); fr["fx"] = fx or []
    return fr

ANIMS = {}

ANIMS["wave"] = [
    F(),
    F(EL=(78, 62), HL=(82, 48)),
    F(EL=(78, 62), HL=(74, 48)),
    F(EL=(78, 62), HL=(88, 48)),
]

ANIMS["cheer"] = [
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),
      EL=(56, 70), HL=(54, 84), ER=(72, 70), HR=(74, 84)),
    F(dy=-8, EL=(54, 56), HL=(48, 40), ER=(74, 56), HR=(80, 40),
      KL=(56, 104), FL=(52, 120), KR=(72, 104), FR=(76, 120)),
    F(dy=-16, EL=(52, 50), HL=(42, 32), ER=(76, 50), HR=(86, 32),
      KL=(54, 102), FL=(46, 116), KR=(74, 102), FR=(82, 116)),
    F(dy=-14, EL=(52, 50), HL=(44, 34), ER=(76, 50), HR=(84, 34),
      KL=(58, 104), FL=(52, 118), KR=(70, 104), FR=(76, 118)),
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),
      EL=(54, 58), HL=(48, 44), ER=(74, 58), HR=(80, 44)),
    F(),
]

LEAN = dict(N=(62, 46), SH=(62, 58), H=(60, 34))
ANIMS["fight_stance"] = [
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(54, 72), HL=(44, 62), ER=(66, 70), HR=(56, 60), **LEAN),
    F(HIP=(64, 91), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),
      EL=(54, 74), HL=(44, 65), ER=(66, 72), HR=(56, 63), **LEAN),
]
ANIMS["fight_punch"] = [
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(46, 62), HL=(30, 60), ER=(66, 70), HR=(56, 60), **LEAN,
      fx=[("speed", (38, 60))]),
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(54, 72), HL=(44, 64), ER=(50, 62), HR=(32, 58), **LEAN,
      fx=[("speed", (40, 58))]),
]
ANIMS["fight_kick"] = [
    F(N=(66, 46), SH=(68, 56), H=(70, 42), HIP=(66, 84),
      KR=(68, 104), FR=(68, 123), KL=(44, 88), FL=(26, 78),
      EL=(76, 66), HL=(82, 76), ER=(72, 62), HR=(78, 52),
      fx=[("speed", (36, 82))]),
]
ANIMS["fight_block"] = [
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),
      EL=(56, 74), HL=(50, 60), ER=(60, 78), HR=(50, 70), **LEAN),
]

ANIMS["sword"] = [
    F(EL=(54, 68), HL=(50, 86), fx=[("sword", "HL", 75)]),
    F(EL=(48, 56), HL=(46, 44), fx=[("sword", "HL", -130)]),
    F(EL=(44, 60), HL=(38, 62),
      fx=[("sword", "HL", 50), ("arc", (20, 40, 80, 100), 200, 340)]),
    F(EL=(46, 66), HL=(40, 72),
      fx=[("sword", "HL", 8), ("arc", (16, 52, 84, 92), 170, 350)]),
    F(EL=(54, 68), HL=(50, 84), fx=[("sword", "HL", 60)]),
]

ANIMS["mine"] = [
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 84),
      EL=(58, 60), HL=(58, 50), ER=(68, 56), HR=(64, 46),
      fx=[("pick", (62, 46), (40, 20))]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 88),
      EL=(52, 72), HL=(44, 84), ER=(60, 70), HR=(50, 80),
      fx=[("pick", (48, 80), (30, 108))]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 88),
      EL=(52, 72), HL=(44, 84), ER=(60, 70), HR=(50, 80),
      fx=[("pick", (48, 80), (30, 108)), ("burst", (30, 112), 12),
          ("chips", [(36, 104), (24, 100), (40, 96)])]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 86),
      EL=(56, 64), HL=(52, 66), ER=(64, 62), HR=(58, 60),
      fx=[("pick", (56, 62), (44, 40))]),
]

# sleep: head rests on folded arm (pillow), limbs separated so it stays readable
SLEEP_J = dict(H=(26, 110), N=(38, 112), SH=(50, 114), HIP=(80, 116),
               EL=(38, 122), HL=(30, 118), ER=(62, 108), HR=(72, 110),
               KL=(98, 112), FL=(114, 114), KR=(94, 122), FR=(108, 123))
ANIMS["sleep"] = [
    F(fx=[("z", (46, 88), 0.9, 255)], **SLEEP_J),
    F(fx=[("z", (46, 88), 0.9, 200), ("z", (56, 72), 1.2, 255)], **SLEEP_J),
    F(fx=[("z", (46, 88), 0.9, 150), ("z", (58, 70), 1.2, 220),
        ("z", (72, 50), 1.6, 255)], **SLEEP_J),
]

# hurt: clearly sitting up, hands planted, legs out front
HURT_J = dict(H=(52, 74), N=(54, 84), SH=(54, 94), HIP=(64, 114),
              KL=(86, 116), FL=(106, 122), KR=(88, 109), FR=(108, 115),
              EL=(46, 104), HL=(44, 118), ER=(62, 104), HR=(64, 118))
ANIMS["hurt"] = [
    F(fx=[("stars", 0)], **HURT_J),
    F(fx=[("stars", 1)], **HURT_J),
    F(dx=2, HIP=(64, 84), KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123),
      EL=(56, 70), HL=(54, 84), ER=(72, 70), HR=(74, 84)),
]

ANIMS["cursorslash"] = [
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),
      EL=(52, 62), HL=(46, 50), fx=[("sword", "HL", -60)]),
    F(dy=-14, EL=(54, 48), HL=(46, 32), ER=(74, 60), HR=(80, 48),
      KL=(56, 102), FL=(48, 116), KR=(72, 102), FR=(80, 116),
      fx=[("sword", "HL", -45), ("arc", (24, 0, 104, 60), 180, 360),
          ("speed", (60, 30))]),
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),
      EL=(54, 66), HL=(48, 60), fx=[("sword", "HL", 30)]),
]

ANIMS["glitch"] = [F(), F(dx=2), F(dx=-2)]

# ---------------- NEW BATCH ----------------
# backflip: special-cased rotation (see render_frame)
ANIMS["flip"] = [
    F(cant_rotate=False, HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107),
      FR=(78, 123), EL=(56, 70), HL=(54, 84), ER=(72, 70), HR=(74, 84)),
    F(cant_rotate=False, dy=-16, EL=(52, 52), HL=(44, 36), ER=(76, 52), HR=(84, 36),
      KL=(56, 104), FL=(50, 118), KR=(72, 104), FR=(78, 118)),
    F(flip=(60, -26)),
    F(flip=(150, -28)),
    F(flip=(245, -20)),
    F(cant_rotate=False, HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107),
      FR=(78, 123), EL=(54, 58), HL=(48, 44), ER=(74, 58), HR=(80, 44)),
]
FLIP_BASE = dict(H=(64, 32), N=(64, 42), SH=(64, 54), HIP=(64, 82),
                 EL=(56, 62), HL=(52, 74), ER=(72, 62), HR=(76, 74),
                 KL=(56, 100), FL=(54, 114), KR=(72, 100), FR=(74, 114))

ANIMS["snack"] = [
    F(ER=(72, 68), HR=(75, 82), fx=[("apple", (80, 86), False)]),
    F(ER=(72, 62), HR=(70, 56), fx=[("apple", (71, 48), False)]),
    F(dy=1, ER=(72, 62), HR=(70, 56),
      fx=[("apple", (71, 48), True), ("crumbs", [(62, 52), (80, 54), (70, 60)])]),
    F(ER=(72, 68), HR=(75, 82), fx=[("apple", (80, 86), True)]),
]

ANIMS["slide"] = [
    F(N=(66, 44), SH=(68, 56), H=(70, 40), HIP=(66, 90),                             # lean-in
      KL=(52, 106), FL=(44, 122), KR=(76, 104), FR=(80, 121),
      EL=(74, 68), HL=(80, 80), ER=(72, 64), HR=(78, 54),
      fx=[("speed", (90, 90))]),
    F(N=(60, 60), SH=(62, 72), H=(58, 56), HIP=(64, 100),                            # low slide
      KL=(42, 114), FL=(24, 121), KR=(50, 112), FR=(34, 120),
      EL=(72, 84), HL=(80, 100), ER=(70, 80), HR=(78, 94),
      fx=[("dust", (88, 116), 5), ("dust", (98, 110), 3), ("speed", (100, 80))]),
    F(N=(60, 60), SH=(62, 72), H=(58, 56), HIP=(64, 100),
      KL=(42, 114), FL=(24, 121), KR=(50, 112), FR=(34, 120),
      EL=(72, 84), HL=(80, 100), ER=(70, 80), HR=(78, 94),
      fx=[("dust", (92, 116), 6), ("speed", (100, 80))]),
    F(),                                                                             # recover
]

PUSH_UP = dict(SH=(52, 94), HIP=(88, 94), N=(40, 92), H=(30, 90),
               EL=(48, 106), HL=(46, 119), ER=(56, 106), HR=(54, 119),
               KL=(100, 104), FL=(112, 120), KR=(102, 104), FR=(114, 120))
PUSH_DOWN = dict(SH=(52, 103), HIP=(88, 100), N=(40, 101), H=(30, 99),
                 EL=(38, 108), HL=(46, 119), ER=(62, 108), HR=(54, 119),
                 KL=(100, 108), FL=(112, 120), KR=(102, 108), FR=(114, 120))
ANIMS["pushup"] = [F(**PUSH_UP), F(**PUSH_DOWN), F(**PUSH_UP), F(**PUSH_DOWN)]

ANIMS["sneeze"] = [
    F(H=(66, 26), N=(65, 38), SH=(64, 52), EL=(54, 64), HL=(50, 78),                 # inhale
      ER=(74, 64), HR=(78, 78)),
    F(H=(58, 34), N=(60, 44), SH=(62, 56), EL=(54, 68), HL=(50, 80),                 # ACHOO!
      ER=(70, 68), HR=(68, 80),
      fx=[("achoo", (44, 36))]),
    F(),                                                                             # recover
]

ANIMS["plane"] = [
    F(ER=(74, 60), HR=(80, 48), fx=[("plane_at", (80, 44))]),                        # hold it up
    F(ER=(70, 64), HR=(52, 62), EL=(58, 66), HL=(56, 80),                            # THROW!
      fx=[("plane_at", (28, 52)), ("speed", (44, 52))]),
    F(fx=[("plane_at", (10, 46))]),                                                 # soaring away
    F(),                                                                             # admire
]

# ---- signatures ----
STAR_C = (90, 64)
ANIMS["draw"] = [
    F(ER=(72, 64), HR=(80, 66), fx=[("pencil", STAR_C, 20), ("starpath", 0.3, False)]),
    F(ER=(72, 64), HR=(82, 64), fx=[("pencil", STAR_C, 0), ("starpath", 0.55, False)]),
    F(ER=(72, 64), HR=(80, 68), fx=[("pencil", STAR_C, -20), ("starpath", 0.8, False)]),
    F(ER=(72, 64), HR=(82, 66), fx=[("pencil", STAR_C, 10), ("starpath", 1.0, False)]),
    F(ER=(72, 62), HR=(84, 60), fx=[("starpath", 1.0, True),
        ("sparkles", [(78, 52), (102, 56), (90, 80)], 5)]),
    F(ER=(74, 58), HR=(86, 52), fx=[("starpath", 1.0, True),
        ("sparkles", [(76, 50), (104, 54), (90, 82), (90, 44)], 7)]),
]

ANIMS["tinker"] = [
    F(HIP=(64, 94), KL=(56, 108), FL=(50, 123), KR=(72, 114), FR=(82, 123),
      SH=(64, 60), N=(64, 48), H=(64, 36), ER=(70, 74), HR=(76, 88),
      fx=[("wrench", "HR", 40)]),
    F(HIP=(64, 94), KL=(56, 108), FL=(50, 123), KR=(72, 114), FR=(82, 123),
      SH=(64, 60), N=(64, 48), H=(64, 36), ER=(70, 74), HR=(78, 86),
      fx=[("wrench", "HR", 55), ("redstone", 0)]),
    F(HIP=(64, 94), KL=(56, 108), FL=(50, 123), KR=(72, 114), FR=(82, 123),
      SH=(64, 60), N=(64, 48), H=(64, 36), ER=(70, 74), HR=(76, 88),
      fx=[("wrench", "HR", 40), ("burst", (84, 96), 10)]),
    F(HIP=(64, 94), KL=(56, 108), FL=(50, 123), KR=(72, 114), FR=(82, 123),
      SH=(64, 60), N=(64, 48), H=(64, 36), ER=(70, 74), HR=(78, 86),
      fx=[("wrench", "HR", 55), ("redstone", 1)]),
]

ANIMS["potion"] = [
    F(ER=(72, 68), HR=(74, 76), fx=[("flask", "HR")]),
    F(ER=(74, 64), HR=(78, 66), fx=[("flask", "HR"), ("bubbles", 0)]),
    F(ER=(76, 58), HR=(82, 54), fx=[("flask", "HR"), ("bubbles", 1)]),
    F(ER=(76, 58), HR=(82, 54), fx=[("flask", "HR"), ("bubbles", 1),
                                    ("sparkles", [(72, 40), (94, 44)], 5)]),
]

ANIMS["music"] = [
    F(EL=(66, 66), HL=(78, 60), ER=(62, 76), HR=(54, 86), fx=[("guitar",), ("notes", 0)]),
    F(EL=(66, 66), HL=(78, 60), ER=(62, 76), HR=(58, 88), fx=[("guitar",), ("notes", 0)]),
    F(EL=(68, 64), HL=(82, 58), ER=(62, 76), HR=(54, 86), fx=[("guitar",), ("notes", 1)]),
    F(EL=(68, 64), HL=(82, 58), ER=(62, 76), HR=(58, 88), fx=[("guitar",), ("notes", 1)]),
]

COMMON = ["wave", "cheer", "fight_stance", "fight_punch", "fight_kick", "fight_block",
          "sword", "mine", "sleep", "hurt", "cursorslash", "glitch",
          "flip", "snack", "slide", "pushup", "sneeze", "plane"]
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
        elif k == "stars":
            phase = fx[1]
            cx, cy = joints["H"]
            for i in range(3):
                a = math.radians(phase * 60 + i * 120)
                sparkle(d, (cx + 20 * math.cos(a), cy - 16 + 7 * math.sin(a)), 4)
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
            base = [(88, 100), (94, 94), (82, 92), (90, 106)] if ph == 0 else \
                   [(90, 98), (96, 102), (84, 96), (92, 90)]
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
                note(d, (96, 44), 1.0); note(d, (106, 58), 0.8)
            else:
                note(d, (100, 38), 0.9); note(d, (110, 52), 1.0)
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

def glitch_post(im, seed):
    "thin slice displacement + a few transparent chips (flickers per frame)"
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
