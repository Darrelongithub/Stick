#!/usr/bin/env python3
"""Append new AvA actions + behaviors to each character's Shimeji-ee XML.

Inserts new <Action> blocks before </ActionList> and new <Behavior> blocks
after the Dance behavior (or before </BehaviorList> as fallback).
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
    return lines

def seq_action(name, refs):
    lines = [f'\t\t<Action Name="{name}" Type="Sequence" Loop="false">']
    for r in refs:
        lines.append(f'\t\t\t<ActionReference Name="{r}" />')
    return lines + ['\t\t</Action>', '']

# ---------------- common actions ----------------
COMMON_ACTIONS = []
COMMON_ACTIONS += action("Wave", "Animate", "Floor", [
    ("wave01.png", 6), ("wave02.png", 4), ("wave03.png", 3), ("wave04.png", 3),
    ("wave03.png", 3), ("wave04.png", 3), ("wave01.png", 5)])
COMMON_ACTIONS += action("Cheer", "Animate", "Floor", [
    ("cheer01.png", 3), ("cheer02.png", 2), ("cheer03.png", 3),
    ("cheer04.png", 3), ("cheer05.png", 3), ("cheer06.png", 5)])
COMMON_ACTIONS += action("FightCombo", "Animate", "Floor", [
    ("fight_stance01.png", 4), ("fight_stance02.png", 4), ("fight_punch01.png", 2),
    ("fight_punch02.png", 2), ("fight_stance01.png", 3), ("fight_kick01.png", 4),
    ("fight_block01.png", 4), ("fight_stance02.png", 4)])
COMMON_ACTIONS += action("SwordPractice", "Animate", "Floor", [
    ("sword01.png", 5), ("sword02.png", 3), ("sword03.png", 2),
    ("sword04.png", 2), ("sword03.png", 2), ("sword04.png", 2), ("sword05.png", 5)])
COMMON_ACTIONS += action("Mine", "Animate", "Floor", [
    ("mine01.png", 4), ("mine02.png", 2), ("mine03.png", 4), ("mine04.png", 3),
    ("mine01.png", 3), ("mine02.png", 2), ("mine03.png", 5)])
COMMON_ACTIONS += action("Sleep", "Stay", "Floor", [
    ("sleep01.png", 10), ("sleep02.png", 10), ("sleep03.png", 25)])
COMMON_ACTIONS += action("Hurt", "Animate", "Floor", [
    ("hurt01.png", 6), ("hurt02.png", 6), ("hurt01.png", 5), ("hurt03.png", 10)])
COMMON_ACTIONS += action("CursorSlash", "Animate", "Floor", [
    ("cursorslash01.png", 3), ("cursorslash02.png", 3), ("cursorslash02.png", 2),
    ("cursorslash03.png", 5)])
COMMON_ACTIONS += action("GlitchOut", "Animate", "Floor", [
    ("glitch01.png", 2), ("glitch02.png", 2), ("glitch03.png", 2),
    ("glitch01.png", 2), ("glitch03.png", 4)])
COMMON_ACTIONS += seq_action("BattleRage", ["FightCombo", "SwordPractice", "CursorSlash"])
COMMON_ACTIONS += seq_action("Bonk", ["Hurt", "Stand"])

SIG_ACTIONS = {
    "Orange": action("DrawAlive", "Animate", "Floor", [
        ("draw01.png", 4), ("draw02.png", 4), ("draw03.png", 4),
        ("draw04.png", 4), ("draw05.png", 5), ("draw06.png", 7)]),
    "Yellow": action("Tinker", "Animate", "Floor", [
        ("tinker01.png", 4), ("tinker02.png", 4), ("tinker03.png", 3),
        ("tinker02.png", 3), ("tinker04.png", 5)]),
    "Blue": action("BrewPotion", "Animate", "Floor", [
        ("potion01.png", 5), ("potion02.png", 4), ("potion03.png", 4), ("potion04.png", 6)]),
    "Green": action("PlayGuitar", "Stay", "Floor", [
        ("music01.png", 4), ("music02.png", 4), ("music03.png", 4), ("music04.png", 4)]),
}

# ---------------- behaviors ----------------
def behavior(name, freq, action_ref, cond=None):
    c = f' Condition="{cond}"' if cond else ''
    return ['', f'\t\t<Behavior Name="{name}" Frequency="{freq}"{c}>',
            f'\t\t\t<ActionReference Name="{action_ref}" />', '\t\t</Behavior>']

CURSOR_NEAR = ("${Math.abs(mascot.anchor.x - mascot.environment.cursor.x) &lt; 300 "
               "&amp;&amp; Math.abs(mascot.anchor.y - mascot.environment.cursor.y) &lt; 300}")

COMMON_BEHAVIORS = []
COMMON_BEHAVIORS += behavior("WaveHello", 40, "Wave")
COMMON_BEHAVIORS += behavior("Cheerful", 30, "Cheer")
COMMON_BEHAVIORS += behavior("Sparring", 25, "BattleRage")
COMMON_BEHAVIORS += behavior("SwordTraining", 25, "SwordPractice")
COMMON_BEHAVIORS += behavior("Mining", 30, "Mine")
COMMON_BEHAVIORS += behavior("Nap", 18, "Sleep")
COMMON_BEHAVIORS += behavior("CursorBattle", 40, "CursorSlash", CURSOR_NEAR)
COMMON_BEHAVIORS += behavior("GlitchSurvive", 12, "GlitchOut")
COMMON_BEHAVIORS += behavior("Bonked", 10, "Bonk")

SIG_BEHAVIORS = {
    "Orange": behavior("DrawingAlive", 30, "DrawAlive"),
    "Yellow": behavior("RedstoneTinker", 30, "Tinker"),
    "Blue": behavior("PotionBrewing", 30, "BrewPotion"),
    "Green": behavior("GuitarSolo", 30, "PlayGuitar"),
}

DANCE_ANCHOR = '<Behavior Name="Dance"'

def patch_actions(path, extra):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    # idempotency: skip if already patched
    if 'Name="Wave"' in raw:
        print(f"  {path}: already patched, skipping")
        return
    block = eol.join(['\t\t<!-- AvA custom animations (Stick pack generator) -->'] + extra)
    assert "</ActionList>" in raw
    raw = raw.replace("</ActionList>", block + eol + "\t</ActionList>")
    with open(path, "wb") as f:
        f.write(raw.encode("utf-8"))
    print(f"  {path}: actions added")

def patch_behaviors(path, extra):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    if 'Name="WaveHello"' in raw:
        print(f"  {path}: already patched, skipping")
        return
    block = eol.join(['\t\t<!-- AvA custom behaviors (Stick pack generator) -->'] + extra)
    idx = raw.find(DANCE_ANCHOR)
    if idx != -1:
        end = raw.find("</Behavior>", idx) + len("</Behavior>")
        raw = raw[:end] + eol + block + raw[end:]
    else:
        assert "</BehaviorList>" in raw
        raw = raw.replace("</BehaviorList>", block + eol + "\t</BehaviorList>")
    with open(path, "wb") as f:
        f.write(raw.encode("utf-8"))
    print(f"  {path}: behaviors added")

def main():
    for char in CHARS:
        print(char)
        a_path = os.path.join(ROOT, char, "conf", "actions.xml")
        b_path = os.path.join(ROOT, char, "conf", "behaviors.xml")
        patch_actions(a_path, COMMON_ACTIONS + SIG_ACTIONS[char])
        patch_behaviors(b_path, COMMON_BEHAVIORS + SIG_BEHAVIORS[char])
        # validate: every new image referenced exists; XML parses
        tree = ET.parse(a_path)
        names = set()
        ET.parse(b_path)
        for pose_el in tree.getroot().iter():
            if pose_el.tag.endswith("Pose") and pose_el.get("Image"):
                names.add(pose_el.get("Image").lstrip("/"))
        missing = [n for n in sorted(names)
                   if n.split(".")[0].rsplit("0", 1)[0] + "0" in ()]  # placeholder
        # check only our new files
        new_prefixes = ("wave", "cheer", "fight_", "sword", "mine", "sleep", "hurt",
                        "cursorslash", "glitch", "draw", "tinker", "potion", "music")
        missing = [n for n in sorted(names)
                   if n.startswith(new_prefixes)
                   and not os.path.exists(os.path.join(ROOT, char, n))]
        if missing:
            print(f"  MISSING IMAGES in {char}: {missing}")
            sys.exit(1)
        print(f"  {char}: XML valid, all new images present")

if __name__ == "__main__":
    main()
