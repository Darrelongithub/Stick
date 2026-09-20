#!/usr/bin/env python3
"""Append new AvA actions + behaviors to each character's Shimeji-ee XML.

Per-name idempotent: only inserts actions/behaviors not already present.
Preserves CRLF line endings. Validates XML after patching.
"""
import os, sys, xml.etree.ElementTree as ET

ROOT = "AVA Shimejis"
CHARS = ["Blue", "Orange", "Yellow", "Green"]

def pose(img, dur, vx=0, vy=0, anchor="64,128"):
    return (f'\t\t\t\t<Pose Image="/{img}" ImageAnchor="{anchor}" '
            f'Velocity="{vx},{vy}" Duration="{dur}" />')

def action(name, type_, border, poses):
    lines = [f'\t\t<Action Name="{name}" Type="{type_}" BorderType="{border}">',
             '\t\t\t<Animation>'] + [pose(*p) for p in poses] + \
            ['\t\t\t</Animation>', '\t\t</Action>', '']
    return (name, lines)

def seq_action(name, refs):
    lines = [f'\t\t<Action Name="{name}" Type="Sequence" Loop="false">']
    for r in refs:
        lines.append(f'\t\t\t<ActionReference Name="{r}" />')
    return (name, lines + ['\t\t</Action>', ''])

def behavior(name, freq, action_ref, cond=None):
    c = f' Condition="{cond}"' if cond else ''
    return (name, ['', f'\t\t<Behavior Name="{name}" Frequency="{freq}"{c}>',
            f'\t\t\t<ActionReference Name="{action_ref}" />', '\t\t</Behavior>'])

CURSOR_NEAR = ("${Math.abs(mascot.anchor.x - mascot.environment.cursor.x) &lt; 300 "
               "&amp;&amp; Math.abs(mascot.anchor.y - mascot.environment.cursor.y) &lt; 300}")

# ---------------- actions ----------------
COMMON_ACTIONS = [
    action("Wave", "Animate", "Floor", [
        ("wave01.png", 6), ("wave02.png", 4), ("wave03.png", 3), ("wave04.png", 3),
        ("wave03.png", 3), ("wave04.png", 3), ("wave01.png", 5)]),
    action("Cheer", "Animate", "Floor", [
        ("cheer01.png", 3), ("cheer02.png", 2), ("cheer03.png", 3),
        ("cheer04.png", 3), ("cheer05.png", 3), ("cheer06.png", 5)]),
    action("FightCombo", "Animate", "Floor", [
        ("fight_stance01.png", 4), ("fight_stance02.png", 4), ("fight_punch01.png", 2),
        ("fight_punch02.png", 2), ("fight_stance01.png", 3), ("fight_kick01.png", 4),
        ("fight_block01.png", 4), ("fight_stance02.png", 4)]),
    action("SwordPractice", "Animate", "Floor", [
        ("sword01.png", 5), ("sword02.png", 3), ("sword03.png", 2),
        ("sword04.png", 2), ("sword03.png", 2), ("sword04.png", 2), ("sword05.png", 5)]),
    action("Mine", "Animate", "Floor", [
        ("mine01.png", 4), ("mine02.png", 2), ("mine03.png", 4), ("mine04.png", 3),
        ("mine01.png", 3), ("mine02.png", 2), ("mine03.png", 5)]),
    action("Sleep", "Stay", "Floor", [
        ("sleep01.png", 10), ("sleep02.png", 10), ("sleep03.png", 25)]),
    action("Hurt", "Animate", "Floor", [
        ("hurt01.png", 6), ("hurt02.png", 6), ("hurt01.png", 5), ("hurt03.png", 10)]),
    action("CursorSlash", "Animate", "Floor", [
        ("cursorslash01.png", 3), ("cursorslash02.png", 3), ("cursorslash02.png", 2),
        ("cursorslash03.png", 5)]),
    action("GlitchOut", "Animate", "Floor", [
        ("glitch01.png", 2), ("glitch02.png", 2), ("glitch03.png", 2),
        ("glitch01.png", 2), ("glitch03.png", 4)]),
    seq_action("BattleRage", ["FightCombo", "SwordPractice", "CursorSlash"]),
    seq_action("Bonk", ["Hurt", "Stand"]),
    # --- batch 2 ---
    action("Backflip", "Animate", "Floor", [
        ("flip01.png", 3), ("flip02.png", 2), ("flip03.png", 2),
        ("flip04.png", 2), ("flip05.png", 2), ("flip06.png", 4)]),
    action("SnackTime", "Animate", "Floor", [
        ("snack01.png", 5), ("snack02.png", 4), ("snack03.png", 5),
        ("snack03.png", 4), ("snack04.png", 5)]),
    action("PowerSlide", "Animate", "Floor", [
        ("slide01.png", 3), ("slide02.png", 3), ("slide03.png", 4), ("slide04.png", 5)]),
    action("PushUps", "Animate", "Floor", [
        ("pushup01.png", 4), ("pushup02.png", 4), ("pushup01.png", 4),
        ("pushup02.png", 4), ("pushup01.png", 5)]),
    action("Sneeze", "Animate", "Floor", [
        ("sneeze01.png", 6), ("sneeze02.png", 4), ("sneeze02.png", 3), ("sneeze03.png", 5)]),
    action("PaperPlane", "Animate", "Floor", [
        ("plane01.png", 5), ("plane02.png", 3), ("plane03.png", 5), ("plane04.png", 5)]),
]

SIG_ACTIONS = {
    "Orange": [action("DrawAlive", "Animate", "Floor", [
        ("draw01.png", 4), ("draw02.png", 4), ("draw03.png", 4),
        ("draw04.png", 4), ("draw05.png", 5), ("draw06.png", 7)])],
    "Yellow": [action("Tinker", "Animate", "Floor", [
        ("tinker01.png", 4), ("tinker02.png", 4), ("tinker03.png", 3),
        ("tinker02.png", 3), ("tinker04.png", 5)])],
    "Blue": [action("BrewPotion", "Animate", "Floor", [
        ("potion01.png", 5), ("potion02.png", 4), ("potion03.png", 4), ("potion04.png", 6)])],
    "Green": [action("PlayGuitar", "Stay", "Floor", [
        ("music01.png", 4), ("music02.png", 4), ("music03.png", 4), ("music04.png", 4)])],
}

COMMON_BEHAVIORS = [
    behavior("WaveHello", 40, "Wave"),
    behavior("Cheerful", 30, "Cheer"),
    behavior("Sparring", 25, "BattleRage"),
    behavior("SwordTraining", 25, "SwordPractice"),
    behavior("Mining", 30, "Mine"),
    behavior("Nap", 18, "Sleep"),
    behavior("CursorBattle", 40, "CursorSlash", CURSOR_NEAR),
    behavior("GlitchSurvive", 12, "GlitchOut"),
    behavior("Bonked", 10, "Bonk"),
    # --- batch 2 ---
    behavior("Backflipper", 20, "Backflip"),
    behavior("SnackBreak", 25, "SnackTime"),
    behavior("Slider", 22, "PowerSlide"),
    behavior("Workout", 20, "PushUps"),
    behavior("Achoo", 15, "Sneeze"),
    behavior("PaperPilot", 20, "PaperPlane"),
]

SIG_BEHAVIORS = {
    "Orange": [behavior("DrawingAlive", 30, "DrawAlive")],
    "Yellow": [behavior("RedstoneTinker", 30, "Tinker")],
    "Blue": [behavior("PotionBrewing", 30, "BrewPotion")],
    "Green": [behavior("GuitarSolo", 30, "PlayGuitar")],
}

DANCE_ANCHOR = '<Behavior Name="Dance"'

def patch_actions(path, wanted):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    missing = [(n, l) for n, l in wanted if f'Name="{n}"' not in raw]
    if not missing:
        print(f"  {path}: actions up to date")
        return
    block = eol.join(['\t\t<!-- AvA custom animations (Stick pack generator) -->'] +
                     [ln for _, l in missing for ln in l])
    assert "</ActionList>" in raw
    raw = raw.replace("</ActionList>", block + eol + "\t</ActionList>")
    with open(path, "wb") as f:
        f.write(raw.encode("utf-8"))
    print(f"  {path}: +{len(missing)} actions {[n for n, _ in missing]}")

def patch_behaviors(path, wanted):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    missing = [(n, l) for n, l in wanted if f'Name="{n}"' not in raw]
    if not missing:
        print(f"  {path}: behaviors up to date")
        return
    block = eol.join(['\t\t<!-- AvA custom behaviors (Stick pack generator) -->'] +
                     [ln for _, l in missing for ln in l])
    idx = raw.find(DANCE_ANCHOR)
    if idx != -1:
        # insert after the LAST custom behavior if present, else after Dance
        anchor = raw.rfind('<Behavior Name="PaperPilot"')
        if anchor == -1:
            anchor = idx
        end = raw.find("</Behavior>", anchor) + len("</Behavior>")
        raw = raw[:end] + eol + block + raw[end:]
    else:
        assert "</BehaviorList>" in raw
        raw = raw.replace("</BehaviorList>", block + eol + "\t</BehaviorList>")
    with open(path, "wb") as f:
        f.write(raw.encode("utf-8"))
    print(f"  {path}: +{len(missing)} behaviors {[n for n, _ in missing]}")

def main():
    prefixes = ("wave", "cheer", "fight_", "sword", "mine", "sleep", "hurt",
                "cursorslash", "glitch", "draw", "tinker", "potion", "music",
                "flip", "snack", "slide", "pushup", "sneeze", "plane")
    for char in CHARS:
        print(char)
        a_path = os.path.join(ROOT, char, "conf", "actions.xml")
        b_path = os.path.join(ROOT, char, "conf", "behaviors.xml")
        patch_actions(a_path, COMMON_ACTIONS + SIG_ACTIONS[char])
        patch_behaviors(b_path, COMMON_BEHAVIORS + SIG_BEHAVIORS[char])
        tree = ET.parse(a_path)
        ET.parse(b_path)
        names = {p.get("Image").lstrip("/") for p in tree.getroot().iter()
                 if p.tag.endswith("Pose") and p.get("Image")}
        missing = [n for n in sorted(names) if n.startswith(prefixes)
                   and not os.path.exists(os.path.join(ROOT, char, n))]
        if missing:
            print(f"  MISSING IMAGES in {char}: {missing}")
            sys.exit(1)
        print(f"  {char}: XML valid, all new images present")

if __name__ == "__main__":
    main()
