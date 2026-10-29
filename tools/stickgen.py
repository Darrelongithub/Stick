#!/usr/bin/env python3
"""Procedural Shimeji frame generator for the AvA stick figures.

Poses are authored in a 128x128 space (centre x=64, floor y=128) and rendered
onto a 160x160 canvas padded by 16px on every side - see tools/ava_common.py.
That padding is deliberate: a generated frame can never have its art touching
the canvas edge, so no limb can be sliced in half and no frame can poke out of
its window. Every rendered frame is asserted to sit inside that margin.

Canvas 160x160, feet anchored at (80,144). Primitives render at 4x by default
and box-filter down for edges matching the stock art (AVA_SS=1 is the geometry
/debug mode). Body color varies per character; props keep fixed colors.
"""
import glob, math, os, re, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ava_common as SPEC

PAD = SPEC.PAD                   # 16   slack around the authoring box
OUT = SPEC.CANVAS                # 160  size of a rendered frame
POSE_OFF = 8                     # 8px grace: poses may reach past the box
BIG = 320                        # scratch canvas for whole-figure rotation
W = H = SPEC.POSE_CANVAS + 2 * POSE_OFF   # 144 - the drawing canvas

# Poses are authored against a 128x128 box (centre x=64, floor y=128) but are
# drawn onto a canvas POSE_OFF px larger on every side, so a pose that reaches
# slightly past the box (feet 1px under the floor line, a sword tip flying up)
# is still *real* art rather than art clipped by the canvas.  The finished
# canvas is then centred in the 160px frame, which is what makes
# "art can never touch the edge of its frame" verifiable.

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

# ---------------------------------------------------------------- drawing helpers
# Anti-aliasing: every drawing primitive is rendered on a canvas SS times the
# pose size and box-filtered back down before it is composited.  Drawing 1x
# with ImageDraw gives hard stair-stepped edges, which is what made the new
# frames look jagged next to the anti-aliased stock art.  SS=1 gives the old
# hard-edged output (useful as a geometry check).
SS = int(os.environ.get("AVA_SS", "4"))

def new_canvas(size=None):
    if isinstance(size, int):
        size = (size, size)
    return Image.new("RGBA", size or (W, H), (0, 0, 0, 0))

def draw_canvas():
    """Supersampled drawing canvas (SS x the pose size)."""
    return Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))

def flatten(im):
    """Box-filter a supersampled canvas back to 1x (anti-aliased edges)."""
    if SS == 1:
        return im
    return im.resize((im.width // SS, im.height // SS), Image.BOX)

def _i(v):
    """Round a coordinate.  Points (tuples) are shifted by POSE_OFF so every
    drawing helper can keep working in plain pose coordinates."""
    if isinstance(v, (tuple, list)):
        return tuple(int(round((c + POSE_OFF) * SS)) for c in v)
    return int(round(v * SS))

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
        d.line(pts + [pts[0]], fill=outline + (255,), width=_i(1))

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
    im = draw_canvas()
    draw_figure(ImageDraw.Draw(im), color, dy=dy, dx=dx, **j)
    return flatten(im)

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

def puff(d, pos, s=1.0, color=None):
    """Little cloud of breath / yawn air."""
    color = color or P["white"]
    x, y = pos
    dot(d, (x, y), 3.4*s, color, 210)
    dot(d, (x+3.6*s, y-1.6*s), 2.7*s, color, 190)
    dot(d, (x+6.4*s, y+0.6*s), 2.1*s, color, 165)
    dot(d, (x-3.2*s, y+1.2*s), 2.3*s, color, 175)

def wind(d, pos, phase=0):
    """Air streaks - a falling body pushes past them."""
    x, y = pos
    for i, oy in enumerate((-9, 0, 9)):
        ln = 10 + 4 * ((i + phase) % 3)
        seg(d, (x, y + oy), (x, y + oy + ln), 2, P["white"], 200)

def rings(d, center, phase, n=2):
    """Calm expanding rings (meditation)."""
    x, y = center
    for i in range(n):
        r = 7 + 6 * ((phase + i) % 3)
        d.ellipse([_i((x - r, y - r * 0.45)), _i((x + r, y + r * 0.45))],
                  outline=P["glass"] + (170 - 30 * i,), width=_i(1))

def phone_prop(d, pos, tap=False, glow=True):
    """Phone held in one hand: body, screen, and an optional tap spark."""
    x, y = pos
    poly(d, [(x-5, y-8), (x+5, y-8), (x+5, y+8), (x-5, y+8)], P["ink"])
    poly(d, [(x-4, y-7), (x+4, y-7), (x+4, y+7), (x-4, y+7)],
         P["glass"] if glow else P["steel_d"], alpha=235)
    seg(d, (x-2, y-5), (x+2, y-5), 1, P["white"])
    seg(d, (x-2, y-2), (x+1, y-2), 1, P["white"])
    if tap:
        dot(d, (x+3, y+3), 2, P["white"], 230)
        sparkle(d, (x+7, y+6), 3, P["spark"])

def mug(d, pos, tilt=0):
    """Coffee mug seen from the side, optional tilt while sipping."""
    x, y = pos
    w = 7
    poly(d, [(x-w, y-7), (x+w, y-7), (x+w, y+6), (x-w, y+6)], P["red"], outline=P["ink"])
    poly(d, [(x-w+1, y-6), (x+w-1, y-6), (x+w-1, y-3), (x-w+1, y-3)], P["grip"])
    if tilt:
        arc(d, (x+w, y-4, x+w+7, y+3), 300, 60, 2, P["red"])
    else:
        arc(d, (x+w, y-4, x+w+7, y+3), 290, 70, 2, P["red"])

def steam(d, base, phase, n=3):
    """S-curve steam wisps above a mug."""
    x, y = base
    for i in range(n):
        off = (i - 1) * 4
        s = 3 + 2 * ((phase + i) % 2)
        seg(d, (x + off, y), (x + off + s, y - 5), 1, P["white"], 200)
        seg(d, (x + off + s, y - 5), (x + off, y - 10), 1, P["white"], 150)

def tear(d, pos, a=255):
    """A fat drop: light core with a bright highlight, so it reads against the
    character's own (blue) body colour."""
    x, y = pos
    dot(d, (x, y), 3, (90, 190, 255), a)
    dot(d, (x, y), 2, (200, 240, 255), a)
    dot(d, (x - 1, y - 1), 1, (255, 255, 255), a)

def beckon(d, hand, phase):
    """\"bring it on\" curls next to a hand"""
    x, y = hand
    for i in range(3):
        r = 4 + 3 * i + (phase % 2)
        arc(d, (x - r, y - r, x + r, y + r), 200, 330, 2, P["white"], 220 - 40 * i)

def bubble(d, pos, mark="!", s=1.0, color=None):
    """Speech bubble with a small mark inside (taunt / cry / victory)."""
    color = color or P["white"]
    x, y = pos
    dot(d, (x, y), 8*s, color)
    dot(d, (x - 7*s, y + 7*s), 2.4*s, color)
    poly(d, [(x-1.6*s, y-5*s), (x+1.6*s, y-5*s), (x+1.6*s, y+1.6*s),
             (x-1.6*s, y+1.6*s)], P["ink"])
    dot(d, (x, y+4.2*s), 1.4*s, P["ink"])
    if mark == "?":
        dot(d, (x, y-3.4*s), 2.2*s, P["ink"])
        dot(d, (x, y-0.4*s), 1.1*s, P["ink"])
    elif mark == "...":
        for i in range(3):
            dot(d, (x - 4*s + i*4*s, y), 1.2*s, P["ink"])

def confetti(d, seed, warm=6, spread=52, top=44):
    """Multicolour burst bits - celebration."""
    import random as _r
    rnd = _r.Random(seed)
    cols = [P["spark"], P["red"], P["liquid"], P["glass"], P["gold"], P["white"]]
    for i in range(warm):
        x = 64 + rnd.randint(-spread, spread)
        y = top + rnd.randint(-8, 30)
        c = cols[i % len(cols)]
        if rnd.random() < 0.5:
            dot(d, (x, y), 2, c)
        else:
            seg(d, (x, y), (x + rnd.choice((-3, 3)), y + 3), 2, c)

def balls(d, pts, r=3, phase=0):
    """Juggling balls, one colour each so the arcs read at a glance."""
    cols = [P["spark"], P["red"], P["liquid"]]
    for i, p in enumerate(pts):
        dot(d, p, r, cols[(i + phase) % len(cols)])
        dot(d, (p[0]-1, p[1]-1), max(1, r-2), P["white"], 150)

def popstar(d, pos, r, phase=0):
    """Star burst that grows and fades - used for potion/sneeze/cheer pops."""
    burst(d, pos, r + phase, core=P["white"], outer=P["spark"])


def book_prop(d, pos, page=0):
    """Small open book with a visible spine and moving page line."""
    x, y = pos
    poly(d, [(x-18, y-9), (x-2, y-6), (x, y+8), (x-17, y+4)],
         P["cream"], outline=P["ink"])
    poly(d, [(x+18, y-9), (x+2, y-6), (x, y+8), (x+17, y+4)],
         P["cream"], outline=P["ink"])
    seg(d, (x, y-6), (x, y+8), 2, P["grip"])
    off = (-10, 8, -6, 11)[page % 4]
    seg(d, (x + off, y-4), (x + off * 0.8, y+1), 1, P["lead"], 190)


def magnifier(d, pos, angle=-25, glint=False):
    """Magnifying glass used by Yellow's inspection move."""
    x, y = pos
    a = math.radians(angle)
    dx, dy = math.cos(a), math.sin(a)
    ellipse(d, (x, y), 8, 8, P["glass"], 90, outline=P["steel_d"], ow=3)
    seg(d, (x-dx*6, y-dy*6), (x-dx*20, y-dy*20), 4, P["grip"])
    if glint:
        sparkle(d, (x+4, y-4), 4, P["white"])


def rope_prop(d, phase=0):
    """Jump rope sweeping around the body; fractional phases stay smooth."""
    a = 2 * math.pi * (phase % 12) / 12
    top = 35 + 8 * math.sin(a)
    bottom = 124 - 6 * math.sin(a)
    width = 38 + 5 * math.cos(a)
    color = P["white"] if math.sin(a) >= 0 else P["steel_d"]
    alpha = 225 if math.sin(a) >= 0 else 145
    arc(d, (64-width, top, 64+width, bottom), 190, 350, 2, color, alpha)
    arc(d, (64-width, top, 64+width, bottom), 10, 170, 2, color, alpha)


# ---------------------------------------------------------------- poses
def F(fx=None, **kw):
    fr = dict(kw); fr["fx"] = fx or []
    return fr

FLIP_BASE = dict(H=(64, 32), N=(64, 42), SH=(64, 54), HIP=(64, 82),
                 EL=(56, 62), HL=(52, 74), ER=(72, 62), HR=(76, 74),
                 KL=(56, 100), FL=(54, 114), KR=(72, 100), FR=(74, 114))

def FLIP(angle, dy):
    """Backflip frame: the tucked body rotated about its middle, lifted by dy."""
    return F(rot=(angle, 64, 78, ("center", dy)), **FLIP_BASE)

def ROT(joints, angle, cx, cy, place, fx=None):
    """Tumble / spin / wobble: `joints` rotated about (cx,cy).

    place is ("ground", y) to rest the result on the floor line, or
    ("center", dy) to hang it in the air, lifted by dy.
    """
    fr = dict(joints)
    fr["rot"] = (angle, cx, cy, place)
    fr["fx"] = fx or []
    return fr


def _full_joints(frame):
    """Resolve a pose to absolute joints, including its dx/dy offset."""
    g = dict(STAND)
    g.update({k: v for k, v in frame.items() if k in STAND})
    dx, dy = frame.get("dx", 0), frame.get("dy", 0)
    return {k: (p[0] + dx, p[1] + dy) for k, p in g.items()}


def tween_pose(a, b, t=0.5):
    """Vector in-between for two ordinary stick poses.

    Props/effects switch at the midpoint while every body joint follows a
    linear path. This remains useful for the tiny breathing idle; high-motion
    cycles below use continuous kinematic rigs instead.
    """
    ga, gb = _full_joints(a), _full_joints(b)
    out = {k: (ga[k][0] + (gb[k][0] - ga[k][0]) * t,
               ga[k][1] + (gb[k][1] - ga[k][1]) * t) for k in STAND}
    out["fx"] = list((a if t < 0.5 else b).get("fx", []))
    return out


def tween_cycle(keys, inbetweens=1):
    """Insert vector in-betweens after every key, including loop closure."""
    out = []
    for i, frame in enumerate(keys):
        out.append(frame)
        target = keys[(i + 1) % len(keys)]
        for step in range(1, inbetweens + 1):
            out.append(tween_pose(frame, target, step / (inbetweens + 1)))
    return out


def rotate_joints(joints, angle, center=(64, 76)):
    """Rotate fully-authored joints without rotating/rasterizing the canvas."""
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    cx, cy = center
    out = {}
    for name, (x, y) in joints.items():
        x, y = x - cx, y - cy
        out[name] = (cx + x * ca - y * sa, cy + x * sa + y * ca)
    return out


def polar(origin, length, angle):
    """Endpoint of a fixed-length limb at ``angle`` radians."""
    return (origin[0] + math.cos(angle) * length,
            origin[1] + math.sin(angle) * length)


def joint_between(start, end, upper, lower, prefer="max_x"):
    """Two-bone inverse kinematics with a stable visual bend direction.

    Keeping limb lengths fixed avoids the rubber-arm effect produced by linear
    interpolation. ``positive``/``negative`` select one continuous branch;
    directional preferences remain useful for non-cyclic authored poses.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    distance = max(1e-6, math.hypot(dx, dy))
    reach = min(max(distance, abs(upper - lower) + 1e-6), upper + lower - 1e-6)
    ux, uy = dx / distance, dy / distance
    along = (upper * upper - lower * lower + reach * reach) / (2 * reach)
    height = math.sqrt(max(0.0, upper * upper - along * along))
    base = (start[0] + ux * along, start[1] + uy * along)
    perp = (-uy * height, ux * height)
    choices = ((base[0] + perp[0], base[1] + perp[1]),
               (base[0] - perp[0], base[1] - perp[1]))
    if prefer == "positive":
        return choices[0]
    if prefer == "negative":
        return choices[1]
    if prefer == "min_x":
        return min(choices, key=lambda point: point[0])
    if prefer == "min_y":
        return min(choices, key=lambda point: point[1])
    if prefer == "max_y":
        return max(choices, key=lambda point: point[1])
    return max(choices, key=lambda point: point[0])


def _hermite(start, end, start_slope, end_slope, t):
    """Cubic Hermite interpolation used for a contact limb's recovery arc."""
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * start
            + (t3 - 2 * t2 + t) * start_slope
            + (-2 * t3 + 3 * t2) * end
            + (t3 - t2) * end_slope)


def contact_track(phase, start, end, fixed, lift, axis="x", lift_sign=-1,
                  stance=0.625):
    """A seamless plant-and-recovery path for a hand or foot.

    During the planted five-eighths of the cycle, the local contact point moves by the
    exact opposite of the sprite velocity, so it stays fixed on the floor,
    ceiling, or wall in screen space. The recovery uses a C1-continuous Hermite
    arc: no teleport at lift-off and no snap when contact is made again.
    """
    phase %= 1.0
    if phase < stance:
        q = phase / stance
        moving = start + (end - start) * q
        other = fixed
    else:
        q = (phase - stance) / (1.0 - stance)
        slope = (end - start) / stance * (1.0 - stance)
        moving = _hermite(end, start, slope, slope, q)
        other = fixed + lift_sign * lift * math.sin(math.pi * q) ** 2
    return (moving, other) if axis == "x" else (other, moving)


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
    # The leap used to be dy=-14 with the blade swung to -45deg: sword and arc
    # flew clean off the top of the canvas and were sliced off.  Lower leap,
    # shallower swing, arc pulled down into frame.
    F(dy=-8, EL=(56, 50), HL=(50, 40), ER=(74, 60), HR=(80, 48),
      KL=(56, 102), FL=(48, 118), KR=(72, 102), FR=(80, 118),
      fx=[("sword", "HL", -35), ("arc", (28, 6, 100, 62), 180, 360),
          ("speed", (58, 34))]),
    F(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),
      EL=(54, 66), HL=(48, 60), fx=[("sword", "HL", 30)]),
]

ANIMS["glitch"] = [F(), F(dx=2), F(dx=-2)]

# ---------------- NEW BATCH ----------------
# backflip: whole-figure rotation, see render_frame()
ANIMS["flip"] = [
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107),
      FR=(78, 123), EL=(56, 70), HL=(54, 84), ER=(72, 70), HR=(74, 84)),
    F(dy=-16, EL=(52, 52), HL=(44, 36), ER=(76, 52), HR=(84, 36),
      KL=(56, 104), FL=(50, 118), KR=(72, 104), FR=(78, 118)),
    FLIP(60, -26),
    FLIP(150, -28),
    FLIP(245, -20),
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107),
      FR=(78, 123), EL=(54, 58), HL=(48, 44), ER=(74, 58), HR=(80, 44)),
]

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
    # The plane is drawn 12px to the left of its own position, so the old
    # "soaring away" frame put half of it off the canvas.  It now shrinks as it
    # flies, which keeps every pixel of it inside the frame.
    F(ER=(74, 60), HR=(80, 48), fx=[("plane_at", (78, 44), 1.0)]),
    F(ER=(70, 64), HR=(52, 62), EL=(58, 66), HL=(56, 80),
      fx=[("plane_at", (36, 52), 0.9), ("speed", (52, 52))]),
    F(fx=[("plane_at", (26, 48), 0.6), ("plane_at", (16, 44), 0.4)]),
    F(ER=(76, 56), HR=(86, 50), fx=[("plane_at", (14, 42), 0.3)]),
]

# ================================================================ new batch
# ---- re-drawn pack actions -------------------------------------------------
# The pack's original art for these had real defects: Yellow's fall frames were
# 161px wide with the throwing arm sliced off at the canvas edge, Green's hang
# frames dangled 211px below the ceiling (2.3x everyone else's), Blue's lay01
# was cut on both sides, and Orange's wall_climb legs sank up to 19px below the
# wall anchor so they were chopped off by the bottom of the screen.  They are
# re-rendered here so the whole crew falls, hangs, lies and climbs alike, and
# so every one of those frames is inside its frame by construction.

# Falling is sampled directly from a continuous rig. The old revision linearly
# blended eight rotated drawings, which shortened limbs between keys and made
# the tumble pulse. Here every limb keeps its authored length while the whole
# body turns through an even 360 degrees, with a secondary flutter in the arms
# and legs so it reads as air resistance rather than a rigid cartwheel.
def FALL_FRAME(index, count=48):
    phase = 2 * math.pi * index / count
    shoulder = (64, 52)
    hip = (64, 79)
    joints = {
        "H": (64, 27), "N": (64, 40), "SH": shoulder, "HIP": hip,
    }
    joints["EL"] = polar(shoulder, 18, 2.85 + 0.34 * math.sin(phase * 2))
    joints["HL"] = polar(joints["EL"], 20,
                         3.45 + 0.58 * math.cos(phase * 2 + 0.35))
    joints["ER"] = polar(shoulder, 18, 0.28 - 0.34 * math.sin(phase * 2))
    joints["HR"] = polar(joints["ER"], 20,
                         -0.35 - 0.58 * math.cos(phase * 2 + 0.35))
    joints["KL"] = polar(hip, 22, 2.05 + 0.28 * math.cos(phase * 2))
    joints["FL"] = polar(joints["KL"], 23,
                         1.86 + 0.52 * math.sin(phase * 2 + 0.6))
    joints["KR"] = polar(hip, 22, 1.09 - 0.28 * math.cos(phase * 2))
    joints["FR"] = polar(joints["KR"], 23,
                         1.28 - 0.52 * math.sin(phase * 2 + 0.6))
    angle = index * 360.0 / count + 3.0 * math.sin(phase * 2)
    return F(**rotate_joints(joints, angle, (64, 67)))


ANIMS["fall"] = [FALL_FRAME(i) for i in range(48)]


def CEILING_HOLD_FRAME(index, count=16):
    """A quiet two-hand pendulum used while waiting on the ceiling."""
    phase = 2 * math.pi * index / count
    angle = 0.10 * math.sin(phase) + 0.035 * math.cos(phase)
    ux, uy = math.sin(angle), math.cos(angle)
    shoulder = (63 + 2.5 * math.sin(phase) + 0.7 * math.cos(phase),
                40 + 1.5 * math.cos(phase))
    hip = (shoulder[0] + ux * 32, shoulder[1] + uy * 32)
    neck = (shoulder[0] - ux * 12, shoulder[1] - uy * 12)
    head = (neck[0] - ux * 12, neck[1] - uy * 12)
    left_hand, right_hand = (32, 1), (94, 1)
    left_elbow = joint_between(shoulder, left_hand, 31, 31, "negative")
    right_elbow = joint_between(shoulder, right_hand, 31, 31, "positive")
    leg_axis = math.pi / 2 + angle
    left_knee = polar(hip, 23, leg_axis + 0.28)
    left_foot = polar(left_knee, 24, leg_axis + 0.16 + 0.08 * math.sin(phase))
    right_knee = polar(hip, 23, leg_axis - 0.28)
    right_foot = polar(right_knee, 24, leg_axis - 0.16 - 0.08 * math.sin(phase))
    return F(H=head, N=neck, SH=shoulder, HIP=hip,
             EL=left_elbow, HL=left_hand, ER=right_elbow, HR=right_hand,
             KL=left_knee, FL=left_foot, KR=right_knee, FR=right_foot)


ANIMS["hang"] = [CEILING_HOLD_FRAME(i) for i in range(16)]


# True hand-over-hand brachiation. A planted palm counter-moves by 1 px per
# host tick, exactly cancelling the action's screen velocity; the other hand
# follows a smooth recovery arc. The torso hangs as a pendulum beneath the
# support and the legs kick through each transfer instead of dangling straight.
def CEILING_SWING_FRAME(index, count=48):
    t = index / count
    step = 4 * math.pi * t
    # Separate hand lanes keep the silhouette readable as one palm passes the
    # other: the old shared lane made both arms collapse across the face.
    left_hand = contact_track(t, 32, 62, 1, 17, lift_sign=1)
    right_hand = contact_track(t + 0.5, 70, 100, 1, 17, lift_sign=1)

    # Build the body as a real pendulum under the grip line. The previous
    # shoulder/hip sine waves barely changed their relative angle, so the pose
    # looked like a standing figure with raised arms instead of a swing.
    swing_angle = 0.62 * math.sin(step - 0.25)
    ux, uy = math.sin(swing_angle), math.cos(swing_angle)
    shoulder = (64 + 7 * math.sin(step - 0.25),
                40 + 2 * math.cos(step))
    hip = (shoulder[0] + ux * 32, shoulder[1] + uy * 32)
    neck = (shoulder[0] - ux * 12, shoulder[1] - uy * 12)
    head = (neck[0] - ux * 12, neck[1] - uy * 12)

    # Bent arms visibly transfer the load; fixed IK lengths prevent rubbery
    # forearms even at the widest part of the swing.
    left_elbow = joint_between(shoulder, left_hand, 31, 31, "negative")
    right_elbow = joint_between(shoulder, right_hand, 31, 31, "positive")

    # Fixed-length legs follow the pendulum with a delayed kick. Their lower
    # segments alternately tuck and extend, but never pop between IK branches.
    leg_axis = math.pi / 2 + swing_angle - 0.20 * math.sin(step - 0.70)
    pump = math.cos(step)
    lower_sweep = 0.18 * pump
    left_knee = polar(hip, 23, leg_axis + 0.28)
    left_foot = polar(left_knee, 23 - 3 * pump,
                      leg_axis + 0.16 + lower_sweep)
    right_knee = polar(hip, 23, leg_axis - 0.28)
    right_foot = polar(right_knee, 23 + 3 * pump,
                       leg_axis - 0.16 + lower_sweep)

    return F(H=head, N=neck, SH=shoulder, HIP=hip,
             EL=left_elbow, HL=left_hand, ER=right_elbow, HR=right_hand,
             KL=left_knee, FL=left_foot, KR=right_knee, FR=right_foot)


ANIMS["swing"] = [CEILING_SWING_FRAME(i) for i in range(48)]


# Wall climbing uses the same planted-contact rule in the vertical direction.
# Each supporting hand/foot moves down locally by 1 px while the sprite moves
# up by 1 px, so it grips the wall instead of skating over it. Reversing these
# frames for descent preserves the contact automatically.
def WALL_CLIMB_FRAME(index, count=48):
    t = index / count
    step = 4 * math.pi * t
    left_hand = contact_track(t, 20, 50, 1, 11, axis="y", lift_sign=1)
    right_hand = contact_track(t + 0.5, 24, 54, 1, 11,
                               axis="y", lift_sign=1)
    left_foot = contact_track(t + 0.5, 78, 108, 2, 12,
                              axis="y", lift_sign=1)
    right_foot = contact_track(t, 76, 106, 2, 12,
                               axis="y", lift_sign=1)

    # Keep the torso visibly away from the wall. Crowding it against x=38 made
    # all four bent limbs collapse into one diamond-shaped knot.
    shoulder = (52 + 3 * math.sin(step), 53 + 3 * math.cos(step))
    hip = (57 + 5 * math.sin(step - 0.45),
           82 + 3 * math.cos(step - 0.20))
    neck = (51 + 3 * math.sin(step - 0.12), shoulder[1] - 12)
    head = (53 + 4 * math.sin(step - 0.18), neck[1] - 13)
    # Side-view limbs get separate visual lanes. Exact circular IK made the
    # near/far limbs fold through each other whenever their holds traded height;
    # these continuously moving midpoints preserve a clean climbing silhouette.
    left_elbow = (39 + 2 * math.sin(step),
                  (shoulder[1] + left_hand[1]) / 2 - 3)
    right_elbow = (45 + 2 * math.sin(step + 0.4),
                   (shoulder[1] + right_hand[1]) / 2 + 3)
    left_knee = (41 + 3 * math.sin(step - 0.3),
                 (hip[1] + left_foot[1]) / 2 - 3)
    right_knee = (50 + 3 * math.sin(step + 0.3),
                  (hip[1] + right_foot[1]) / 2 + 3)
    return F(H=head, N=neck, SH=shoulder, HIP=hip,
             EL=left_elbow, HL=left_hand, ER=right_elbow, HR=right_hand,
             KL=left_knee, FL=left_foot, KR=right_knee, FR=right_foot)


ANIMS["wall_climb"] = [WALL_CLIMB_FRAME(i) for i in range(48)]


def WALL_HOLD_FRAME(index, count=16):
    """Breathing grip loop for pauses between wall-climbing actions."""
    phase = 2 * math.pi * index / count
    sway = math.sin(phase)
    shoulder = (52 + 1.5 * sway, 53 + math.cos(phase))
    hip = (57 + 2 * sway, 82 + math.cos(phase + 0.4))
    neck = (51 + 1.5 * sway, shoulder[1] - 12)
    head = (53 + 2 * sway, neck[1] - 13)
    left_hand, right_hand = (1, 24), (1, 54)
    left_foot, right_foot = (2, 78), (2, 108)
    left_elbow = (39 + sway, (shoulder[1] + left_hand[1]) / 2 - 3)
    right_elbow = (45 - sway, (shoulder[1] + right_hand[1]) / 2 + 3)
    left_knee = (41 + 1.5 * sway, (hip[1] + left_foot[1]) / 2 - 3)
    right_knee = (50 - 1.5 * sway, (hip[1] + right_foot[1]) / 2 + 3)
    return F(H=head, N=neck, SH=shoulder, HIP=hip,
             EL=left_elbow, HL=left_hand, ER=right_elbow, HR=right_hand,
             KL=left_knee, FL=left_foot, KR=right_knee, FR=right_foot)


ANIMS["wall_hold"] = [WALL_HOLD_FRAME(i) for i in range(16)]


def LIE(dy=0, leg=0):
    """Flat on the floor, head to the left (the way the crew faces)."""
    return dict(H=(28, 108 + dy), N=(40, 112 + dy), SH=(50, 114 + dy), HIP=(78, 116 + dy),
             EL=(44, 122 + dy), HL=(34, 124 + dy), ER=(62, 110 + dy), HR=(72, 112 + dy),
             KL=(98, 114 + dy), FL=(116, 118 + dy + leg), KR=(96, 122 + dy),
             FR=(112, 126 + dy - leg))

ANIMS["lay"] = [
    F(**LIE(0, 0)),
    F(**LIE(0, 4)),
    F(**LIE(-1, 0), fx=[("puff", (14, 102), 0.8)]),
]

# trip: stumble -> tumble (rotated) -> face down -> push up -> stand
TRIP_STUMBLE = dict(N=(52, 46), SH=(54, 58), HIP=(62, 82), H=(48, 32),
                    EL=(40, 60), HL=(28, 54), ER=(70, 60), HR=(84, 46),
                    KL=(44, 106), FL=(26, 118), KR=(74, 102), FR=(80, 124))
ANIMS["trip"] = [
    F(fx=[("speed", (98, 62))], **TRIP_STUMBLE),
    ROT(TRIP_STUMBLE, 48, 64, 84, ("ground", 120), fx=[("speed", (92, 74))]),
    ROT(TRIP_STUMBLE, 96, 64, 88, ("ground", 122), fx=[("dust", (92, 122), 4)]),
    F(**LIE(-2, 2), fx=[("dust", (98, 122), 5)]),
    F(**PUSH_UP),
    F(),
]

# ---- new moves -------------------------------------------------------------
# Movement, reactions and idle variety, so the crew stops replaying the same
# five animations at you all afternoon.

# big morning stretch, then a yawn
ANIMS["stretch"] = [
    F(HIP=(64, 84), KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123),
      EL=(58, 68), HL=(56, 84), ER=(70, 68), HR=(72, 84)),
    F(HIP=(64, 82), KL=(58, 104), FL=(53, 124), KR=(70, 104), FR=(75, 124),
      EL=(54, 58), HL=(50, 40), ER=(74, 58), HR=(78, 40)),
    F(HIP=(62, 80), KL=(58, 104), FL=(53, 124), KR=(70, 104), FR=(75, 124),
      EL=(52, 52), HL=(46, 32), ER=(76, 52), HR=(82, 32),
      fx=[("puff", (48, 28), 1.1)]),
    F(HIP=(64, 84), KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123),
      EL=(52, 54), HL=(44, 36), ER=(76, 54), HR=(84, 36),
      fx=[("puff", (44, 30), 0.8), ("puff", (86, 30), 0.8)]),
    F(HIP=(64, 86), KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123),
      EL=(58, 72), HL=(54, 86), ER=(70, 72), HR=(74, 86)),
    F(),
]

# "come at me" - the Animation vs Animator version of trash talk
ANIMS["taunt"] = [
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(54, 72), HL=(44, 62), ER=(66, 70), HR=(56, 60), **LEAN),
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(58, 74), HL=(48, 70), ER=(64, 68), HR=(70, 56), **LEAN,
      fx=[("beckon", (70, 54), 0)]),
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(60, 74), HL=(52, 66), ER=(62, 70), HR=(56, 58), **LEAN,
      fx=[("beckon", (56, 56), 1)]),
    F(HIP=(64, 88), KL=(54, 106), FL=(50, 123), KR=(74, 106), FR=(78, 123),
      EL=(56, 62), HL=(46, 48), ER=(68, 62), HR=(78, 48), **LEAN,
      fx=[("beckon", (44, 46), 0), ("beckon", (80, 46), 1)]),
    F(HIP=(64, 90), KL=(54, 107), FL=(50, 123), KR=(74, 107), FR=(78, 123),
      EL=(56, 70), HL=(50, 60), ER=(68, 72), HR=(62, 62), **LEAN,
      fx=[("bubble", (96, 40), "!", 0.85)]),
    F(),
]

# spinning kick: the whole figure whips through a full turn
SPIN_KICK = dict(N=(64, 44), SH=(64, 56), H=(64, 32), HIP=(64, 86),
                 KL=(52, 104), FL=(48, 122), KR=(76, 104), FR=(80, 122),
                 EL=(50, 68), HL=(40, 60), ER=(78, 70), HR=(90, 74))
ANIMS["spin"] = [
    F(HIP=(64, 92), KL=(54, 108), FL=(50, 123), KR=(74, 108), FR=(78, 123),
      EL=(56, 76), HL=(48, 66), ER=(72, 74), HR=(80, 66), **LEAN),
    # wind up: arms trail behind, weight on the back foot
    F(N=(62, 44), SH=(62, 56), H=(60, 30), HIP=(64, 86),
      KL=(52, 104), FL=(48, 122), KR=(76, 104), FR=(80, 122),
      EL=(46, 62), HL=(34, 54), ER=(80, 64), HR=(92, 56),
      fx=[("speed", (100, 52))]),
    # the kick sweeps through
    F(N=(62, 46), SH=(62, 58), H=(60, 34), HIP=(62, 86),
      KL=(90, 74), FL=(112, 68), KR=(72, 106), FR=(72, 124),
      EL=(46, 66), HL=(34, 58), ER=(74, 72), HR=(70, 86),
      fx=[("speed", (104, 60))]),
    F(N=(64, 46), SH=(64, 58), H=(64, 34), HIP=(62, 86),
      KL=(96, 84), FL=(118, 84), KR=(72, 106), FR=(70, 124),
      EL=(48, 68), HL=(36, 62), ER=(76, 74), HR=(74, 88),
      fx=[("speed", (108, 78))]),
    # ...and lands
    F(N=(64, 44), SH=(64, 56), H=(66, 32), HIP=(64, 86),
      KL=(52, 106), FL=(48, 124), KR=(74, 106), FR=(66, 118),
      EL=(52, 70), HL=(42, 78), ER=(78, 68), HR=(90, 66)),
    F(HIP=(64, 94), KL=(54, 108), FL=(50, 123), KR=(74, 108), FR=(78, 123),
      EL=(52, 78), HL=(42, 84), ER=(76, 78), HR=(86, 84),
      fx=[("dust", (34, 122), 4), ("dust", (94, 122), 4)]),
]

# phone: out of the pocket, thumb scroll, put away
ANIMS["phone"] = [
    F(ER=(70, 78), HR=(74, 92)),
    F(ER=(68, 62), HR=(74, 50), EL=(58, 70), HL=(54, 84),
      fx=[("phone", (76, 50), False)]),
    F(ER=(68, 62), HR=(74, 50), EL=(60, 66), HL=(60, 56),
      fx=[("phone", (76, 50), True)]),
    F(ER=(68, 64), HR=(74, 52), EL=(60, 68), HL=(61, 58),
      fx=[("phone", (76, 52), False), ("speed", (88, 46))]),
    F(ER=(68, 62), HR=(74, 50), EL=(60, 66), HL=(60, 56),
      fx=[("phone", (76, 50), True), ("bubble", (34, 40), "...", 0.95)]),
    F(ER=(70, 78), HR=(74, 92)),
]

# coffee: mug up, steam, sip, satisfied wiggle
ANIMS["coffee"] = [
    F(ER=(72, 68), HR=(76, 80), fx=[("mug", (76, 74), False, 0)]),
    F(ER=(72, 58), HR=(74, 46), fx=[("mug", (74, 40), False, 1)]),
    F(ER=(70, 54), HR=(70, 42), fx=[("mug", (70, 36), False, 2)]),
    F(ER=(70, 52), HR=(68, 40), fx=[("mug", (68, 34), True, 3)]),
    F(ER=(72, 60), HR=(76, 50), fx=[("mug", (78, 46), False, 0),
                                    ("sparkles", [(92, 38), (60, 32)], 4)]),
    F(ER=(72, 70), HR=(76, 82)),
]

# meditation: cross-legged, floating a few pixels, calm rings
MEDITATE = dict(H=(64, 34), N=(64, 46), SH=(64, 58), HIP=(64, 82),
                EL=(50, 72), HL=(48, 90), ER=(78, 72), HR=(80, 90),
                KL=(50, 96), FL=(64, 110), KR=(78, 96), FR=(64, 110))
ANIMS["meditate"] = [
    F(**MEDITATE, fx=[("rings", 0, 1)]),
    F(**{**MEDITATE, "HIP": (64, 84), "N": (64, 44), "H": (64, 32), "EL": (52, 68),
         "ER": (76, 68), "HL": (56, 84), "HR": (72, 84)}, fx=[("rings", 1, 2)]),
    F(**{**MEDITATE, "HIP": (64, 82), "N": (64, 42), "H": (64, 30), "EL": (52, 66),
         "ER": (76, 66), "HL": (56, 82), "HR": (72, 82)},
      fx=[("rings", 2, 2), ("sparkles", [(46, 40), (84, 44)], 4)]),
    F(**{**MEDITATE, "HIP": (64, 84), "N": (64, 44), "H": (64, 32)},
      fx=[("rings", 3, 1)]),
    F(**MEDITATE, fx=[("sparkles", [(88, 52)], 5)]),
    F(**MEDITATE, fx=[("rings", 0, 1)]),
]

# crying: hands to the face, tears, a sniff, then quiet
CRY_STAND = dict(H=(60, 32), N=(61, 42), SH=(62, 54), HIP=(64, 80),
                  EL=(52, 66), HL=(58, 46), ER=(74, 66), HR=(62, 46),
                  KL=(58, 102), FL=(53, 123), KR=(70, 102), FR=(75, 123))
CRY_HUNCH = dict(H=(60, 36), N=(61, 46), SH=(62, 58), HIP=(64, 82),
                 EL=(52, 70), HL=(58, 50), ER=(74, 70), HR=(62, 50),
                 KL=(58, 102), FL=(53, 123), KR=(70, 102), FR=(75, 123))
ANIMS["cry"] = [
    F(**CRY_STAND, fx=[("tear", [(56, 50)], [255])]),
    F(**CRY_HUNCH, fx=[("tear", [(56, 52), (66, 50)], [255, 230])]),
    F(**{**CRY_STAND, "HL": (56, 44), "HR": (64, 44), "H": (60, 30)},
      fx=[("tear", [(54, 54), (68, 52), (60, 50)], [255, 240, 210])]),
    F(**{**CRY_HUNCH, "HL": (58, 48), "HR": (62, 48), "H": (60, 34)},
      fx=[("tear", [(52, 58), (68, 56), (60, 54)], [250, 240, 210])]),
    F(**CRY_STAND, fx=[("puff", (36, 54), 0.9), ("tear", [(56, 54)], [200])]),
    F(**CRY_STAND, fx=[("tear", [(66, 50), (56, 56)], [200, 190]),
                       ("bubble", (92, 34), "...", 0.85)]),
]

# dizzy: staggering about the feet with stars over the head
DIZZY_STAND = dict(HIP=(64, 84), KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123),
                   EL=(52, 70), HL=(44, 82), ER=(76, 70), HR=(84, 82))
DIZZY_WOBBLE = dict(HIP=(64, 88), KL=(56, 106), FL=(52, 123), KR=(72, 106), FR=(76, 123),
                    EL=(46, 74), HL=(34, 76), ER=(82, 74), HR=(94, 76), H=(62, 32))
ANIMS["dizzy"] = [
    ROT(DIZZY_WOBBLE, -7, 64, 122, ("ground", 126), fx=[("stars", 0)]),
    ROT(DIZZY_WOBBLE, 6, 64, 122, ("ground", 126), fx=[("stars", 1)]),
    ROT(DIZZY_WOBBLE, -5, 64, 122, ("ground", 126), fx=[("stars", 2)]),
    ROT(DIZZY_STAND, 4, 64, 122, ("ground", 126), fx=[("stars", 1)]),
    F(HIP=(64, 90), KL=(58, 106), FL=(53, 123), KR=(70, 106), FR=(75, 123),
      EL=(56, 76), HL=(50, 88), ER=(72, 76), HR=(78, 88), H=(64, 34),
      fx=[("stars", 0), ("bubble", (94, 34), "?", 0.7)]),
]

# juggling: three balls, two hands, one very pleased stick figure
# Three-ball cascade: one ball at the apex overhead, one being thrown and one
# caught at chest height.  Ball positions are kept out of the head (which sits
# at 64,32 r12) so nothing ever looks stuck in the character's face.
JUGGLE_BALLS = [
    [(64, 10), (86, 56), (46, 44)],
    [(64, 10), (82, 34), (44, 58)],
    [(64, 10), (88, 46), (46, 60)],
    [(64, 10), (44, 40), (86, 54)],
    [(64, 10), (46, 24), (84, 60)],
    [(64, 10), (42, 52), (86, 56)],
    [(64, 10), (44, 58), (82, 40)],
]
HANDS = [
    ((46, 48), (86, 56)),
    ((46, 56), (84, 36)),
    ((46, 60), (88, 46)),
    ((46, 42), (86, 54)),
    ((48, 28), (84, 58)),
    ((44, 52), (86, 56)),
    ((46, 58), (82, 42)),
]
ANIMS["juggle"] = []
for i, (pts, (hl, hr)) in enumerate(zip(JUGGLE_BALLS, HANDS)):
    ANIMS["juggle"].append(F(
        EL=(hl[0] + 6, 68), HL=hl, ER=(hr[0] - 6, 68), HR=hr,
        HIP=(64, 86), KL=(56, 105), FL=(52, 123), KR=(72, 105), FR=(76, 123),
        fx=[("balls", pts, i % 3)]))

# victory: two fist pumps and a confetti burst
ANIMS["victory"] = [
    F(HIP=(64, 92), KL=(54, 108), FL=(50, 123), KR=(74, 108), FR=(78, 123),
      EL=(52, 78), HL=(46, 90), ER=(76, 78), HR=(82, 90)),
    F(dy=-4, EL=(52, 62), HL=(48, 46), ER=(76, 62), HR=(80, 46),
      KL=(54, 104), FL=(50, 120), KR=(74, 104), FR=(78, 120),
      fx=[("popstar", (44, 38), 6, 0)]),
    F(dy=-8, EL=(50, 56), HL=(44, 38), ER=(78, 56), HR=(84, 38),
      KL=(52, 100), FL=(46, 116), KR=(76, 100), FR=(82, 116),
      fx=[("confetti", 7, 9, 46, 30)]),
    F(dy=-2, EL=(52, 64), HL=(46, 50), ER=(76, 64), HR=(82, 50),
      KL=(56, 104), FL=(52, 120), KR=(72, 104), FR=(76, 120),
      fx=[("confetti", 11, 4, 44, 28)]),
    F(dy=-6, EL=(52, 60), HL=(47, 44), ER=(76, 60), HR=(81, 44),
      KL=(56, 102), FL=(52, 118), KR=(72, 102), FR=(76, 118),
      fx=[("confetti", 9, 5, 40, 34), ("sparkles", [(38, 34), (92, 30)], 4)]),
    F(HIP=(64, 84), KL=(58, 104), FL=(53, 123), KR=(70, 104), FR=(75, 123),
      EL=(54, 62), HL=(46, 48), ER=(74, 62), HR=(82, 48),
      fx=[("sparkles", [(90, 44), (40, 50)], 3)]),
    F(fx=[("sparkles", [(92, 52)], 3)]),
]

# idle: a seamless breath and weight shift.  This cycle is also injected into
# the stock Stand action, replacing its single 10-second statue frame.
IDLE_KEYS = [
    F(),
    F(H=(64, 27), N=(64, 38), SH=(64, 50), HIP=(64, 78),
      EL=(56, 65), HL=(54, 79), ER=(72, 65), HR=(74, 79),
      KL=(58, 102), FL=(53, 123), KR=(70, 102), FR=(75, 123)),
    F(dx=1, H=(65, 28), N=(65, 39), SH=(65, 51), HIP=(65, 80),
      EL=(57, 66), HL=(55, 80), ER=(73, 66), HR=(75, 80),
      KL=(60, 102), FL=(55, 123), KR=(71, 102), FR=(76, 123)),
    F(H=(64, 30), N=(64, 41), SH=(64, 53), HIP=(64, 81),
      EL=(55, 68), HL=(53, 82), ER=(73, 68), HR=(75, 82)),
]
ANIMS["idle"] = tween_cycle(IDLE_KEYS)

# A low crawl that still reads as a *person* on all fours.
#
# The previous rig was the problem: a shoulder line stretched almost
# horizontally (34,91)->(81,98) with straight 30px arms and 32px legs splayed
# off both ends turns the figure into a four-legged insect with its head
# dragging along the floor.  It also had a 37px knee jump at the loop seam.
#
# This rig keeps the human reading the stock art uses: a *short* back
# (55,82)->(78,96), a head held up at the front, and limbs that fold instead of
# spearing out.  Contacts slide backwards at exactly the action's own speed
# (Crawl moves -1px per tick), so a planted hand or foot stays glued to the
# desktop for the whole stance, and each limb recovers on a rounded arc.
CRAWL_STANCE = 0.625             # fraction of the cycle a contact is planted
CRAWL_STEP = 48 * CRAWL_STANCE   # px swept while planted == 1px/tick travel


def crawl_tread(phase, front, lift):
    """Planted contact that travels back at the action velocity, then recovers."""
    phase %= 1.0
    if phase < CRAWL_STANCE:
        return front - CRAWL_STEP * (phase / CRAWL_STANCE), 121.0
    q = (phase - CRAWL_STANCE) / (1.0 - CRAWL_STANCE)
    ease = q * q * (3 - 2 * q)
    return (front - CRAWL_STEP + CRAWL_STEP * ease,
            121.0 - lift * math.sin(math.pi * q))


def GROUND_CRAWL_FRAME(index, count=48):
    t = index / count
    bob = 1.1 * math.cos(4 * math.pi * t)
    head = (34, 64 + bob * 0.5)
    neck = (45, 73 + bob * 0.7)
    shoulder = (55, 82 + bob)
    hip = (78, 96 + bob * 0.5)

    # Diagonal gait: left hand with right foot, right hand with left foot.
    left_hand = crawl_tread(t, 56, 12)
    right_hand = crawl_tread(t + 0.5, 54, 12)
    left_foot = crawl_tread(t + 0.5, 96, 8)
    right_foot = crawl_tread(t, 94, 8)

    # Elbows fold behind the hands and knees fold under the hips: the limbs
    # stay short, close to the body, and below the back line.
    left_elbow = (left_hand[0] + 6, 104 + bob * 0.5)
    right_elbow = (right_hand[0] + 6, 103 + bob * 0.5)
    left_knee = ((left_foot[0] + hip[0]) / 2 + 2, 110 - (121.0 - left_foot[1]) * 0.6)
    right_knee = ((right_foot[0] + hip[0]) / 2 + 1, 111 - (121.0 - right_foot[1]) * 0.6)
    return F(H=head, N=neck, SH=shoulder, HIP=hip,
             EL=left_elbow, HL=left_hand, ER=right_elbow, HR=right_hand,
             KL=left_knee, FL=left_foot, KR=right_knee, FR=right_foot)


ANIMS["crawl"] = [GROUND_CRAWL_FRAME(i) for i in range(48)]

# Orange: a continuously sampled cartwheel. The old twelve-frame version held
# its setup, then jumped 35-45 degrees per drawing. This rigid vector rig turns
# in even 7.5-degree steps with a filtered hand-to-foot support transfer.
CART = dict(H=(64, 25), N=(64, 38), SH=(64, 51), HIP=(64, 78),
            EL=(44, 55), HL=(26, 70), ER=(84, 55), HR=(102, 70),
            KL=(50, 96), FL=(38, 121), KR=(78, 96), FR=(90, 121))


def cartwheel_frames(count=48):
    rigs = [rotate_joints(CART, index * 360.0 / count, (64, 74))
            for index in range(count)]
    lowest = [max(point[1] for point in rig.values()) for rig in rigs]
    shifts = [123 - value for value in lowest]
    # A hard "lowest point = floor" rule jumps when support changes from hand
    # to foot. Circular filtering gives that hand-off a smooth centre-of-mass
    # arc; one global correction keeps every drawing above the floor line.
    for _ in range(4):
        shifts = [(shifts[(i - 1) % count] + 2 * shifts[i]
                   + shifts[(i + 1) % count]) / 4 for i in range(count)]
    overflow = max(lowest[i] + shifts[i] - 123 for i in range(count))
    shifts = [value - overflow for value in shifts]
    return [F(**{name: (point[0], point[1] + shifts[index])
                 for name, point in rig.items()})
            for index, rig in enumerate(rigs)]


ANIMS["cartwheel"] = cartwheel_frames()

# Blue: sit cross-legged and turn a page rather than freezing in another static
# sit pose.  Both hands follow the book over the eight-frame action.
READ_POSE = dict(H=(58, 54), N=(60, 66), SH=(62, 78), HIP=(66, 102),
                 EL=(51, 88), HL=(49, 101), ER=(75, 88), HR=(77, 101),
                 KL=(51, 109), FL=(66, 121), KR=(81, 109), FR=(66, 121))
ANIMS["read"] = [
    F(**READ_POSE, fx=[("book", (64, 98), 0)]),
    F(**{**READ_POSE, "H": (57, 52)}, fx=[("book", (64, 97), 0)]),
    F(**{**READ_POSE, "HR": (71, 94), "ER": (76, 86)}, fx=[("book", (64, 97), 1)]),
    F(**{**READ_POSE, "HR": (63, 91), "ER": (73, 84)}, fx=[("book", (64, 97), 2)]),
    F(**{**READ_POSE, "HR": (54, 95), "ER": (69, 85)}, fx=[("book", (64, 97), 3)]),
    F(**{**READ_POSE, "H": (60, 53), "HR": (72, 99)}, fx=[("book", (64, 98), 0)]),
    F(**READ_POSE, fx=[("book", (64, 98), 1), ("bubble", (96, 60), "...", 0.7)]),
    F(**READ_POSE, fx=[("book", (64, 98), 2)]),
]

# Yellow: inspect a mysterious speck, changing distance and lens angle on every
# beat.  It complements Tinker without reusing the same wrench choreography.
ANIMS["inspect"] = [
    F(ER=(74, 64), HR=(82, 58), fx=[("magnify", (88, 52), -35, False)]),
    F(N=(60, 44), SH=(61, 56), H=(57, 32), HIP=(64, 84),
      ER=(73, 61), HR=(80, 54), fx=[("magnify", (84, 48), -30, False)]),
    F(N=(56, 48), SH=(58, 60), H=(52, 38), HIP=(64, 88),
      ER=(69, 62), HR=(73, 54), EL=(50, 72), HL=(44, 84),
      fx=[("magnify", (77, 48), -20, True)]),
    F(N=(54, 52), SH=(57, 64), H=(49, 42), HIP=(64, 92),
      ER=(66, 65), HR=(68, 57), EL=(48, 76), HL=(42, 88),
      fx=[("magnify", (72, 51), -10, False), ("sparkles", [(82, 45)], 3)]),
    F(N=(56, 48), SH=(58, 60), H=(52, 38), HIP=(64, 88),
      ER=(69, 62), HR=(73, 54), fx=[("magnify", (78, 48), -20, False)]),
    F(ER=(74, 63), HR=(82, 56), fx=[("magnify", (87, 50), -35, True)]),
    F(ER=(74, 68), HR=(78, 78), fx=[("magnify", (84, 74), -55, False),
                                    ("bubble", (98, 38), "!", 0.7)]),
    F(),
]

# Green: one complete rope revolution and jump sampled at the host's full
# 25 fps. A sinusoidal take-off/landing has zero velocity at both seams, while
# the rope accepts half-phases so its oval no longer advances in visible steps.
def JUMP_ROPE_FRAME(index, count=24):
    phase = 2 * math.pi * index / count
    jump = math.sin(phase / 2) ** 2
    lift = -8 * jump
    wrist = 2 * math.sin(phase)
    feet = 3 * jump
    return F(
        dy=lift,
        EL=(50, 66), HL=(40, 77 + wrist),
        ER=(78, 66), HR=(88, 77 - wrist),
        KL=(57, 103), FL=(51 + feet, 121),
        KR=(71, 103), FR=(77 - feet, 121),
        fx=[("rope", index * 12.0 / count)])


ANIMS["jumprope"] = [JUMP_ROPE_FRAME(i) for i in range(24)]

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

# (which animation belongs to which action is declared in tools/ava_common.py;
#  the lists above are only the pose data)

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
                d.line([_i(p) for p in pts[:n]], fill=(255, 240, 170, 255), width=_i(2))
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
            paper_plane(d, fx[1], fx[2] if len(fx) > 2 else 1.0)
        elif k == "wind":
            wind(d, fx[1], fx[2])
        elif k == "puff":
            puff(d, fx[1], fx[2] if len(fx) > 2 else 1.0)
        elif k == "rings":
            rings(d, joints["HIP"], fx[1], fx[2] if len(fx) > 2 else 2)
        elif k == "phone":
            phone_prop(d, fx[1], tap=fx[2])
        elif k == "mug":
            _, pos, tilt, phase = fx
            mug(d, pos, tilt)
            steam(d, (pos[0], pos[1] - 9), phase)
        elif k == "tear":
            for i, tpos in enumerate(fx[1]):
                tear(d, tpos, fx[2][i])
        elif k == "beckon":
            beckon(d, fx[1], fx[2])
        elif k == "bubble":
            bubble(d, fx[1], fx[2], fx[3] if len(fx) > 3 else 1.0)
        elif k == "confetti":
            confetti(d, fx[1], fx[2], fx[3] if len(fx) > 3 else 52)
        elif k == "balls":
            balls(d, fx[1], phase=fx[2] if len(fx) > 2 else 0)
        elif k == "popstar":
            popstar(d, fx[1], fx[2], fx[3] if len(fx) > 3 else 0)
        elif k == "book":
            book_prop(d, fx[1], fx[2])
        elif k == "magnify":
            magnifier(d, fx[1], fx[2], fx[3])
        elif k == "rope":
            rope_prop(d, fx[1])
        elif k == "chips_wood":
            for c in fx[1]:
                dot(d, c, 2, P["wood"])

def glitch_post(im, seed):
    """thin slice displacement + a few transparent chips (flickers per frame)"""
    im = im.copy()
    W4, H4 = im.size
    import random as _r
    rnd = _r.Random(seed)
    for _ in range(3):
        y0 = rnd.randrange(PAD + 20, H4 - PAD - 30)
        h = rnd.randrange(2, 5)
        off = rnd.choice([-6, -4, 4, 6])
        band = im.crop((0, y0, W4, y0 + h))
        im.paste(band, (off, y0))
    d = ImageDraw.Draw(im)
    for _ in range(3):  # transparent chips
        x0 = rnd.randrange(PAD + 40, PAD + 90); y0 = rnd.randrange(PAD + 25, PAD + 115)
        d.rectangle([x0, y0, x0 + rnd.randrange(2, 5), y0 + 1], fill=(0, 0, 0, 0))
    return im

def pad_frame(im):
    """Drawing canvas -> rendered frame, centred with PAD-px margins."""
    out = new_canvas(OUT)
    out.alpha_composite(im, (PAD - POSE_OFF, PAD - POSE_OFF))
    return out

def bounds_error(im, anim, idx):
    """None if the art sits inside the frame's margin, else a report string."""
    box = im.getbbox()
    if box is None:
        return f"{anim}[{idx}]: empty frame"
    l, t, r, b = box
    if l < 1 or t < 1 or r > im.width - 1 or b > im.height - 1:
        return (f"{anim}[{idx}]: art {box} touches the {im.width}x{im.height} "
                f"canvas edge - on screen that limb would be cut in half")
    return None

def check(im, anim, idx, errors, stage):
    err = bounds_error(im, anim, idx)
    if err:
        errors.append(f"{err} ({stage})")
    return im

def render_frame(color_rgb, anim, frame_idx):
    fr = dict(ANIMS[anim][frame_idx])
    fx = fr.pop("fx")
    rot = fr.pop("rot", None)
    if rot is not None:
        # Whole-figure rotation (backflip / tumble / spin / wobble).  The
        # figure turns on an oversized canvas and the result is then *placed*
        # - bottom-aligned to the floor for ground moves, centred for air
        # moves - and clamped into the frame.  Rotating a figure about a point
        # near its feet used to fling the head clean out of the canvas; auto
        # placement is what stops a spin or a face-plant from being beheaded.
        angle, cx, cy, place = rot
        joints = {k: v for k, v in fr.items() if k not in ("dy", "dx", "cant_rotate")}
        flat = figure_layer(color_rgb, **joints)
        S = (BIG - W) // 2
        big = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
        big.alpha_composite(flat, (S, S))
        spun = big.rotate(angle, resample=Image.BICUBIC,
                          center=(S + cx + POSE_OFF, S + cy + POSE_OFF))
        box = spun.getbbox() or (0, 0, 1, 1)
        mode, param = place
        if mode == "ground":
            ty = POSE_OFF + param - box[3]
        else:
            ty = POSE_OFF + SPEC.POSE_CANVAS / 2 + param - (box[1] + box[3]) / 2
        tx = 0
        if box[0] + tx < 1:
            tx = 1 - box[0]
        if box[2] + tx > W - 1:
            tx = (W - 1) - box[2]
        if box[1] + ty < 1:
            ty = 1 - box[1]
        if box[3] + ty > H - 1:
            ty = (H - 1) - box[3]
        im = new_canvas()
        im.alpha_composite(spun, (int(round(tx)), int(round(ty))))
        fx_layer = draw_canvas()
        render_fx(ImageDraw.Draw(fx_layer), fx, dict(STAND))
        im.alpha_composite(flatten(fx_layer))
        return pad_frame(im)
    fr.pop("cant_rotate", None)
    dy = fr.pop("dy", 0); dx = fr.pop("dx", 0)
    im = draw_canvas()
    d = ImageDraw.Draw(im)
    pre = [f for f in fx if f[0] in ("guitar", "balls")]
    post = [f for f in fx if f[0] not in ("guitar", "balls")]
    joints = draw_figure(d, color_rgb, dy=dy, dx=dx, **fr)
    if pre:
        render_fx(d, pre, joints)
        g = dict(STAND); g.update(fr)
        mv = lambda p: (p[0] + dx, p[1] + dy)
        limb(d, [mv(g["SH"]), mv(g["EL"]), mv(g["HL"])], LIMB_W, color_rgb)
    render_fx(d, post, joints)
    out = pad_frame(flatten(im))
    if anim == "glitch":
        out = glitch_post(out, 11 + frame_idx * 5)
    return out

# ---------------------------------------------------------------- main
def anim_frames(action):
    """The ANIMS list backing an action (some actions join several lists)."""
    key = SPEC.ACTIONS[action].get("anim", SPEC.ACTIONS[action]["prefix"])
    if isinstance(key, (tuple, list)):
        out = []
        for k in key:
            out.extend(ANIMS[k])
        return out
    return ANIMS[key]

def managed_prefixes():
    pre = set()
    for a in SPEC.ACTIONS.values():
        if a.get("regen"):
            pre.add(a["prefix"])
            for f in a.get("files", []):
                pre.add(re.sub(r"\d*\.png$", "", f))
    return {p for p in pre if p}

def stale_files(char):
    """Managed-prefix files that this generation no longer produces."""
    want = {f for a in SPEC.generated_actions_for(char) for f in SPEC.frame_names(a)}
    return [f for p in managed_prefixes()
            for f in sorted(glob.glob(f"{OUT_ROOT}/{char}/{p}*.png"))
            if os.path.basename(f) and os.path.basename(f) not in want]

OUT_ROOT = "AVA Shimejis"

# Maximum vector travel of any joint between adjacent 40 ms frames, including
# the last-to-first seam. These are deliberately tighter for planted-contact
# motion than for a foot at the outside of a full-body tumble.
CONTINUITY_LIMITS = {"fall": 12.0, "swing": 7.5, "hang": 2.5,
                     "wall_climb": 4.0, "wall_hold": 1.0, "crawl": 4.0,
                     "cartwheel": 10.5, "jumprope": 2.0}


def continuity_errors():
    errors = []
    for anim, limit in CONTINUITY_LIMITS.items():
        frames = ANIMS[anim]
        for joint in STAND:
            points = [_full_joints(frame)[joint] for frame in frames]
            distances = [math.dist(points[i], points[(i + 1) % len(points)])
                         for i in range(len(points))]
            biggest = max(distances)
            if biggest > limit:
                index = distances.index(biggest)
                errors.append(
                    f"{anim}: {joint} jumps {biggest:.2f}px between "
                    f"frames {index + 1} and {(index + 1) % len(frames) + 1} "
                    f"(limit {limit:.2f}px)")
    return errors


def main(out_root="AVA Shimejis", only=None, preview_dir="preview/new", prune=False):
    global OUT_ROOT
    OUT_ROOT = out_root
    SPEC.self_check()
    os.makedirs(preview_dir, exist_ok=True)
    errors, written, sheets = continuity_errors(), 0, {}
    for char, rgb in BODY.items():
        if only and char not in only:
            continue
        dest = os.path.join(out_root, char)
        os.makedirs(dest, exist_ok=True)
        stale = stale_files(char)
        if stale:
            names = ", ".join(os.path.basename(f) for f in stale)
            if prune:
                for f in stale:
                    os.remove(f)
                print(f"{char}: pruned {len(stale)} stale frame(s): {names}")
            else:
                print(f"{char}: WARNING {len(stale)} stale frame(s): {names}")
        for action in SPEC.generated_actions_for(char):
            frames = anim_frames(action)
            names = SPEC.frame_names(action)
            if len(frames) != len(names):
                errors.append(f"{action}: {len(names)} files but {len(frames)} poses")
                continue
            for i, name in enumerate(names):
                frame = render_frame(rgb, _anim_key_for(action, i), _anim_index(action, i))
                err = bounds_error(frame, action, i)
                if err:
                    errors.append(err)
                frame.save(os.path.join(dest, name))
                written += 1
            # Copy pixels eagerly so hundreds of preview frames do not keep an
            # open file descriptor each (48-frame cycles otherwise exceed the
            # common 1024-fd process limit before Green is rendered).
            preview_frames = []
            for name in names:
                with Image.open(os.path.join(dest, name)) as image:
                    preview_frames.append(image.convert("RGBA").copy())
            sheets.setdefault(action, {})[char] = preview_frames
    build_previews(sheets, preview_dir)
    print(f"wrote {written} frames")
    if errors:
        print("\nGENERATION QUALITY REPORT")
        for e in errors:
            print("  " + e)
        sys.exit(1)
    print("every frame sits inside its margins; cycle continuity limits pass")

def _anim_key_for(action, i):
    key = SPEC.ACTIONS[action].get("anim", SPEC.ACTIONS[action]["prefix"])
    if isinstance(key, (tuple, list)):
        n = 0
        for k in key:
            if i < n + len(ANIMS[k]):
                return k
            n += len(ANIMS[k])
        return key[-1]
    return key

def _anim_index(action, i):
    key = SPEC.ACTIONS[action].get("anim", SPEC.ACTIONS[action]["prefix"])
    if isinstance(key, (tuple, list)):
        n = 0
        for k in key:
            if i < n + len(ANIMS[k]):
                return i - n
            n += len(ANIMS[k])
        return 0
    return i

def build_previews(sheets, preview_dir):
    """Contact sheet per action (all four characters, 2x) + animated strips."""
    for action, per_char in sorted(sheets.items()):
        chars = [c for c in SPEC.CHARS if c in per_char]
        n = max(len(per_char[c]) for c in chars)
        sheet = Image.new("RGBA", (OUT * n, OUT * len(chars)), (40, 40, 44, 255))
        for row, c in enumerate(chars):
            for col, im in enumerate(per_char[c]):
                sheet.alpha_composite(im, (col * OUT, row * OUT))
        sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(
            os.path.join(preview_dir, f"{action.lower()}.png"))
    # Animated previews use Blue when available, otherwise the action's owner.
    for action in sorted(sheets):
        owner = "Blue" if "Blue" in sheets[action] else next(iter(sheets[action]))
        frames = sheets[action][owner]
        gif = [f.convert("RGBA") for f in frames]
        preview_ms = 40 if len(gif) >= 16 else 110
        gif[0].save(os.path.join(preview_dir, f"_{action.lower()}_loop.gif"),
                    save_all=True, append_images=gif[1:], duration=preview_ms, loop=0,
                    disposal=2, transparency=0)

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    only = args[0].split(",") if args else None
    main(only=only, prune="--prune" in flags)
