#!/usr/bin/env python3
"""Procedural Shimeji frame generator - AvA stick figures, crisp supersampled render.

Canvas 128x128, feet anchored at (64,128). Drawn at 4x then downscaled.
Body color varies per character; props keep fixed colors.
"""
import math, os, random, sys
from PIL import Image, ImageDraw

SS = 4                      # supersample factor
W = H = 128
CX, GROUND = 64, 127        # anchor: feet x-center, ground y

BODY = {                    # measured from original pack
    "Blue":   (37, 192, 255),
    "Orange": (242, 111, 36),
    "Yellow": (255, 197, 0),
    "Green":  (95, 183, 0),
}
LIMB_W = 7                  # limb stroke width at 1x
HEAD_R = 12

# fixed prop palette (same for every character)
P = {
    "wood":   (139, 90, 43),
    "wood_d": (90, 55, 20),
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
}

# ---------------------------------------------------------------- helpers
def sc(v):
    "scale 1x coord -> SS canvas"
    if isinstance(v, (tuple, list)):
        return tuple(int(round(c * SS)) for c in v)
    return int(round(v * SS))

def new_canvas():
    return Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))

def finish(im):
    return im.resize((W, H), Image.LANCZOS)

def limb(d, pts, w, color):
    pts = [sc(p) for p in pts]
    d.line(pts, fill=color + (255,), width=sc(w), joint="curve")
    for p in pts:  # round caps / smooth joints
        r = sc(w) / 2
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color + (255,))

def dot(d, pos, r, color, alpha=255):
    p = sc(pos); r = sc(r)
    d.ellipse([p[0]-r, p[1]-r, p[0]+r, p[1]+r], fill=color + (alpha,))

def poly(d, pts, color, alpha=255, outline=None):
    pts = [sc(p) for p in pts]
    d.polygon(pts, fill=color + (alpha,))
    if outline:
        d.line(pts + [pts[0]], fill=outline + (255,), width=max(1, sc(1)))

def seg(d, a, b, w, color, alpha=255):
    d.line([sc(a), sc(b)], fill=color + (alpha,), width=sc(w))

def arc(d, bbox, start, end, w, color, alpha=255):
    x0, y0, x1, y1 = bbox
    d.arc([sc((x0, y0)), sc((x1, y1))], start, end, fill=color + (alpha,), width=sc(w))

def ellipse(d, center, rx, ry, color, alpha=255, outline=None, ow=1):
    c = sc(center); rx, ry = sc(rx), sc(ry)
    box = [c[0]-rx, c[1]-ry, c[0]+rx, c[1]+ry]
    d.ellipse(box, fill=color + (alpha,))
    if outline:
        d.ellipse(box, outline=outline + (255,), width=sc(ow))

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
    "eighth note with dark underlay for visibility"
    x, y = pos
    for col, grow in ((P["ink"], 1.6), (color, 0)):
        ellipse(d, (x, y), 3.4*s+grow, 2.6*s+grow, col)
        seg(d, (x+3.2*s, y-0.5*s), (x+3.2*s, y-9*s), 1.8*s+grow*2, col)
        seg(d, (x+3.2*s, y-9*s), (x+6.5*s, y-7*s), 1.8*s+grow*2, col)

def zee(d, pos, s=1.0, alpha=255):
    "letter Z, white with dark outline"
    x, y = pos
    w, h = 7*s, 8*s
    pts = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
    for col, ww in ((P["ink"], 3.6), ((255,255,255), 2.0)):
        pp = [sc(p) for p in pts]
        d.line(pp, fill=col + (alpha,), width=max(1, int(sc(ww*s))), joint="miter")

# ---------------------------------------------------------------- figure
STAND = dict(
    H=(64, 29), N=(64, 40), SH=(64, 52),
    EL=(57, 67), HL=(55, 81), ER=(71, 67), HR=(73, 81),
    HIP=(64, 80), KL=(59, 102), FL=(53, 123), KR=(69, 102), FR=(75, 123),
)

def draw_figure(d, color, dy=0, dx=0, **j):
    "j overrides STAND joints; dy shifts whole body up (negative = airborne)"
    g = dict(STAND); g.update(j)
    def mv(p):
        return (p[0] + dx, p[1] + dy)
    # far arm, far leg, torso, near leg, head, near arm
    limb(d, [mv(g["SH"]), mv(g["ER"]), mv(g["HR"])], 6, color)
    limb(d, [mv(g["HIP"]), mv(g["KR"]), mv(g["FR"])], LIMB_W, color)
    limb(d, [mv(g["N"]), mv(g["SH"]), mv(g["HIP"])], LIMB_W, color)
    limb(d, [mv(g["HIP"]), mv(g["KL"]), mv(g["FL"])], LIMB_W, color)
    dot(d, mv(g["H"]), HEAD_R, color)
    limb(d, [mv(g["SH"]), mv(g["EL"]), mv(g["HL"])], 6, color)
    return {k: mv(v) for k, v in g.items()}

# ---------------------------------------------------------------- props
def sword(d, hand, angle_deg, flip=False):
    "grip at hand, pointing along angle (deg, 0=+x, -90=up)"
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    px, py = -dy, dx
    hx, hy = hand
    # grip
    seg(d, hand, (hx+dx*7, hy+dy*7), 4, P["grip"])
    dot(d, (hx-dx*1.5, hy-dy*1.5), 2.4, P["gold"])
    # guard
    gx, gy = hx+dx*8, hy+dy*8
    seg(d, (gx-px*6, gy-py*6), (gx+px*6, gy+py*6), 3, P["gold"])
    # blade
    bx, by = gx+dx*2, gy+dy*2
    tip = (bx+dx*30, by+dy*30)
    w = 2.8
    poly(d, [(bx-px*w, by-py*w), (tip[0]-px*w*0.4, tip[1]-py*w*0.4), tip,
             (tip[0]+px*w*0.4, tip[1]+py*w*0.4), (bx+px*w, by+py*w)], P["steel"], outline=P["steel_d"])

def pickaxe(d, top, bottom):
    "handle from top to bottom; head at bottom end"
    seg(d, top, bottom, 4.5, P["wood"])
    # head: perpendicular, pointed ends
    ax, ay = top; bx, by = bottom
    dx, dy = bx-ax, by-ay
    L = math.hypot(dx, dy) or 1
    px, py = -dy/L, dx/L
    cx, cy = bx + dx/L*2, by + dy/L*2
    s = 15
    poly(d, [(cx-px*s, cy-py*s), (cx-px*4, cy-py*4-3), (cx+px*4, cy+py*4-3),
             (cx+px*s, cy+py*s), (cx+px*4, cy+py*4+3), (cx-px*4, cy-py*4+3)],
         P["steel_d",] if False else P["steel"], outline=P["steel_d"])
    dot(d, (cx, cy), 3.4, P["steel_d"])

def guitar(d):
    body_c = (54, 88)
    ellipse(d, body_c, 12, 15, P["guitar"], outline=P["guitar_d"], ow=1.5)
    dot(d, body_c, 4.5, P["hole"])
    seg(d, (60, 78), (90, 50), 5, P["guitar_d"])
    seg(d, (60, 78), (90, 50), 2, P["cream"])
    dot(d, (90, 50), 3.5, P["guitar_d"])

def flask_prop(d, pos):
    x, y = pos  # center of flask body
    poly(d, [(x-3, y-12), (x+3, y-12), (x+6, y-4), (x+6, y+6),
             (x-6, y+6), (x-6, y-4)], P["glass"], outline=P["ink"])
    poly(d, [(x-5, y-1), (x+5, y-1), (x+5, y+5), (x-5, y+5)], P["liquid"])
    seg(d, (x-2.5, y-12), (x+2.5, y-12), 2.5, P["wood_d"])

def wrench(d, hand, angle_deg):
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    hx, hy = hand
    ex, ey = hx+dx*18, hy+dy*18
    seg(d, hand, (ex, ey), 3.5, P["steel_d"])
    dot(d, (ex, ey), 4.5, P["steel_d"])
    dot(d, (ex+dx*3, ey+dy*3), 2.6, (0,0,0), alpha=0)  # notch fake (skip)
    # open end: erase wedge via bg-colored circle segment -> simpler: small gap dot in bg not possible; draw C shape
    dot(d, (ex+dx*2.5, ey+dy*2.5), 2.8, P["steel"])

def pencil(d, tip, angle_deg):
    "tip at drawing point, body extends back along angle"
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    p0 = tip
    p1 = (tip[0]+dx*4, tip[1]+dy*4)
    p2 = (tip[0]+dx*18, tip[1]+dy*18)
    seg(d, p0, p1, 3.2, P["cream"])
    seg(d, p1, p2, 3.6, P["red"])
    dot(d, p0, 1.4, P["lead"])

# ---------------------------------------------------------------- poses
# Each anim: name -> list of frames; frame = dict(joint overrides, dy, dx, fx=[...])
# fx entries: tuples handled in render()
def F(fx=None, **kw):
    fr = dict(kw); fr["fx"] = fx or []
    return fr

ANIMS = {}

ANIMS["wave"] = [
    F(HL=(55, 81)),
    F(EL=(78, 62), HL=(82, 48), fx=[]),
    F(EL=(78, 62), HL=(74, 48), fx=[]),
    F(EL=(78, 62), HL=(88, 48), fx=[]),
]

ANIMS["cheer"] = [
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),
      EL=(56, 70), HL=(54, 84), ER=(72, 70), HR=(74, 84)),                                   # crouch
    F(dy=-8, EL=(54, 56), HL=(48, 40), ER=(74, 56), HR=(80, 40),                             # launch
      KL=(56, 104), FL=(52, 120), KR=(72, 104), FR=(76, 120)),
    F(dy=-16, EL=(52, 50), HL=(42, 32), ER=(76, 50), HR=(86, 32),                            # apex V
      KL=(54, 102), FL=(46, 116), KR=(74, 102), FR=(82, 116)),
    F(dy=-14, EL=(52, 50), HL=(44, 34), ER=(76, 50), HR=(84, 34),
      KL=(58, 104), FL=(52, 118), KR=(70, 104), FR=(76, 118)),
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),                  # land
      EL=(54, 58), HL=(48, 44), ER=(74, 58), HR=(80, 44)),
    F(),                                                                                    # stand
]

LEAN = dict(N=(62, 46), SH=(62, 58), H=(60, 34))
ANIMS["fight_stance"] = [
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(54, 72), HL=(44, 62), ER=(66, 70), HR=(56, 60), **LEAN),
    F(HIP=(64, 91), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),
      EL=(54, 74), HL=(44, 65), ER=(66, 72), HR=(56, 63), **LEAN),
]
ANIMS["fight_punch"] = [
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),                  # jab
      EL=(46, 62), HL=(30, 60), ER=(66, 70), HR=(56, 60), **LEAN,
      fx=[("speed", (38, 60))]),
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),                  # cross
      EL=(54, 72), HL=(44, 64), ER=(50, 62), HR=(32, 58), **LEAN,
      fx=[("speed", (40, 58))]),
]
ANIMS["fight_kick"] = [
    F(N=(66, 46), SH=(68, 56), H=(70, 42), HIP=(66, 84),                                    # kick
      KR=(68, 104), FR=(68, 123), KL=(44, 88), FL=(26, 78),
      EL=(76, 66), HL=(82, 76), ER=(72, 62), HR=(78, 52),
      fx=[("speed", (36, 82))]),
]
ANIMS["fight_block"] = [
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),                  # block
      EL=(56, 74), HL=(50, 60), ER=(60, 78), HR=(50, 70), **LEAN),
]

ANIMS["sword"] = [
    F(EL=(54, 68), HL=(50, 86), fx=[("sword", "HL", 75)]),                                   # idle down
    F(EL=(48, 56), HL=(46, 44), fx=[("sword", "HL", -130)]),                                 # raise
    F(EL=(44, 60), HL=(38, 62), fx=[("sword", "HL", 50), ("arc", (20, 40, 80, 100), 200, 340)]),  # slash \
    F(EL=(46, 66), HL=(40, 72), fx=[("sword", "HL", 8), ("arc", (16, 52, 84, 92), 170, 350)]),    # slash --
    F(EL=(54, 68), HL=(50, 84), fx=[("sword", "HL", 60)]),                                   # recover
]

ANIMS["mine"] = [
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 84),                  # raise
      EL=(58, 60), HL=(58, 50), ER=(68, 56), HR=(64, 46),
      fx=[("pick", (62, 46), (40, 20))]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 88),                  # strike
      EL=(52, 72), HL=(44, 84), ER=(60, 70), HR=(50, 80),
      fx=[("pick", (48, 80), (30, 108))]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 88),                  # impact!
      EL=(52, 72), HL=(44, 84), ER=(60, 70), HR=(50, 80),
      fx=[("pick", (48, 80), (30, 108)), ("burst", (30, 112), 12),
          ("chips", [(36, 104), (24, 100), (40, 96)])]),
    F(FL=(44, 123), FR=(84, 123), KL=(52, 104), KR=(76, 104), HIP=(64, 86),                  # recover
      EL=(56, 64), HL=(52, 66), ER=(64, 62), HR=(58, 60),
      fx=[("pick", (56, 62), (44, 40))]),
]

ANIMS["sleep"] = [
    F(H=(26, 112), N=(38, 114), SH=(50, 116), HIP=(80, 118), EL=(52, 122), HL=(62, 122),
      ER=(58, 110), HR=(68, 112), KL=(96, 114), FL=(112, 116), KR=(96, 122), FR=(112, 122),
      fx=[("z", (46, 88), 0.9, 255)]),
    F(H=(26, 112), N=(38, 114), SH=(50, 116), HIP=(80, 118), EL=(52, 122), HL=(62, 122),
      ER=(58, 110), HR=(68, 112), KL=(96, 114), FL=(112, 116), KR=(96, 122), FR=(112, 122),
      fx=[("z", (46, 88), 0.9, 200), ("z", (56, 72), 1.2, 255)]),
    F(H=(26, 112), N=(38, 114), SH=(50, 116), HIP=(80, 118), EL=(52, 122), HL=(62, 122),
      ER=(58, 110), HR=(68, 112), KL=(96, 114), FL=(112, 116), KR=(96, 122), FR=(112, 122),
      fx=[("z", (46, 88), 0.9, 150), ("z", (58, 70), 1.2, 220), ("z", (72, 50), 1.6, 255)]),
]

ANIMS["hurt"] = [
    F(H=(46, 76), N=(50, 84), SH=(50, 92), HIP=(62, 112),                                   # knocked down
      KL=(82, 114), FL=(102, 121), KR=(84, 108), FR=(104, 115),
      EL=(42, 104), HL=(40, 118), ER=(58, 102), HR=(62, 116),
      fx=[("stars", 0)]),
    F(H=(46, 76), N=(50, 84), SH=(50, 92), HIP=(62, 112),
      KL=(82, 114), FL=(102, 121), KR=(84, 108), FR=(104, 115),
      EL=(42, 104), HL=(40, 118), ER=(58, 102), HR=(62, 116),
      fx=[("stars", 1)]),
    F(dx=2, EL=(56, 70), HL=(54, 84), ER=(72, 70), HR=(74, 84), HIP=(64, 84),                 # wobbly getup
      KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123)),
]

ANIMS["cursorslash"] = [
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),                  # crouch
      EL=(52, 62), HL=(46, 50), fx=[("sword", "HL", -60)]),
    F(dy=-14, EL=(54, 48), HL=(46, 32), ER=(74, 60), HR=(80, 48),                            # LEAP + slash!
      KL=(56, 102), FL=(48, 116), KR=(72, 102), FR=(80, 116),
      fx=[("sword", "HL", -45), ("arc", (24, 0, 104, 60), 180, 360), ("speed", (60, 30))]),
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),                  # land
      EL=(54, 66), HL=(48, 60), fx=[("sword", "HL", 30)]),
]

# glitch handled as post-process on stand/walk-ish poses
ANIMS["glitch"] = [F(), F(dx=3), F(dx=-3)]

# ---- signatures ----
STAR_C = (90, 64)
ANIMS["draw"] = [
    F(ER=(72, 64), HR=(80, 66), fx=[("pencil", STAR_C, 20), ("starpath", 0.3, False)]),
    F(ER=(72, 64), HR=(82, 64), fx=[("pencil", STAR_C, 0), ("starpath", 0.55, False)]),
    F(ER=(72, 64), HR=(80, 68), fx=[("pencil", STAR_C, -20), ("starpath", 0.8, False)]),
    F(ER=(72, 64), HR=(82, 66), fx=[("pencil", STAR_C, 10), ("starpath", 1.0, False)]),
    F(ER=(72, 62), HR=(84, 60), fx=[("starpath", 1.0, True), ("sparkles", [(78, 52), (102, 56), (90, 80)], 5)]),
    F(ER=(74, 58), HR=(86, 52), fx=[("starpath", 1.0, True), ("sparkles", [(76, 50), (104, 54), (90, 82), (90, 44)], 7)]),
]

ANIMS["tinker"] = [
    F(HIP=(64, 94), KL=(56, 108), FL=(50, 123), KR=(72, 114), FR=(82, 123),                  # kneel
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
          "sword", "mine", "sleep", "hurt", "cursorslash", "glitch"]
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
            arc(d, bbox, a0, a1, 9, P["slash"], 90)
            arc(d, bbox, a0, a1, 4, P["white"], 255)
        elif k == "burst":
            _, pos, r = fx
            burst(d, pos, r)
        elif k == "chips":
            for c in fx[1]:
                dot(d, c, 1.8, P["steel_d"])
        elif k == "speed":
            _, (x, y) = fx
            for i, off in enumerate((-6, 0, 6)):
                seg(d, (x - 14, y + off), (x - 4, y + off), 2, P["white"], 200)
        elif k == "z":
            _, pos, s, a = fx
            zee(d, pos, s, a)
        elif k == "stars":
            phase = fx[1]
            cx, cy = joints["H"]
            for i in range(3):
                a = math.radians(phase * 60 + i * 120)
                sparkle(d, (cx + 20 * math.cos(a), cy - 16 + 7 * math.sin(a)), 4.5)
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
                seg_path = [sc(p) for p in pts[:n]]
                d.line(seg_path, fill=(255, 240, 170, 255), width=sc(2))
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
                dot(d, b, 2.2, P["redstone"])
            sparkle(d, base[0], 4)
        elif k == "flask":
            flask_prop(d, (joints[fx[1]][0] + 2, joints[fx[1]][1] - 10))
        elif k == "bubbles":
            ph = fx[1]
            hx, hy = joints["HR"]
            bub = [(hx - 2, hy - 26), (hx + 4, hy - 32)] if ph == 0 else \
                  [(hx - 3, hy - 32), (hx + 3, hy - 40), (hx, hy - 26)]
            for b in bub:
                dot(d, b, 1.8, P["white"])
        elif k == "guitar":
            guitar(d)
        elif k == "notes":
            ph = fx[1]
            if ph == 0:
                note(d, (96, 44), 1.0); note(d, (106, 58), 0.8)
            else:
                note(d, (100, 38), 0.9); note(d, (110, 52), 1.0)

def glitch_post(im):
    "slice displacement + scanline gaps (surviving deletion!)"
    im = im.copy()
    px = im.load()
    W4, H4 = im.size
    rnd = random.Random(7)
    for _ in range(6):
        y0 = rnd.randrange(0, H4 - 20)
        h = rnd.randrange(6, 22)
        off = rnd.choice([-28, -16, 16, 28])
        band = im.crop((0, y0, W4, y0 + h))
        im.paste(band, (off, y0))
    d = ImageDraw.Draw(im)
    for y in range(0, H4, 8):
        d.rectangle([0, y, W4, y + 1], fill=(0, 0, 0, 0))
    return im

def render_frame(color_rgb, anim, frame_idx):
    fr = dict(ANIMS[anim][frame_idx])
    fx = fr.pop("fx")
    dy = fr.pop("dy", 0); dx = fr.pop("dx", 0)
    im = new_canvas()
    d = ImageDraw.Draw(im)
    # guitar goes behind front arm but over torso: draw figure first, guitar after torso?
    # simplest: pre-prop guitar drawn before figure if present
    pre = [f for f in fx if f[0] == "guitar"]
    post = [f for f in fx if f[0] != "guitar"]
    joints = draw_figure(d, color_rgb, dy=dy, dx=dx, **fr)
    # redraw order fix: guitar under arms -> draw now then redraw arms
    if pre:
        render_fx(d, pre, joints)
        g = dict(STAND); g.update(fr)
        mv = lambda p: (p[0] + dx, p[1] + dy)
        limb(d, [mv(g["SH"]), mv(g["EL"]), mv(g["HL"])], 6, color_rgb)
    render_fx(d, post, joints)
    if anim == "glitch":
        im = glitch_post(im)
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
    # contact sheets per anim (first char + all chars row)
    for anim, chars in anims_done.items():
        for char, frames in chars.items():
            sheet = Image.new("RGBA", (128 * len(frames), 128), (40, 40, 40, 255))
            for i, f in enumerate(frames):
                sheet.paste(f, (i * 128, 0), f)
            sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
            sheet.save(os.path.join(preview_dir, f"{anim}_{char}.png"))
    print("done. anims:", sorted(anims_done))

if __name__ == "__main__":
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    main(only=only)
