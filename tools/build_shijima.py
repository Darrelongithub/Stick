#!/usr/bin/env python3
"""Build import-ready zip archives for Shijima-Qt.

Shijima-Qt expects the DefaultMascot layout:
    CharacterName/
    ├── img/
    │   └── (image files)
    ├── actions.xml
    └── behaviors.xml

This script packages each AvA character into that exact layout.

Usage:
    python3 tools/build_shijima.py              # build all four
    python3 tools/build_shijima.py --all        # build per-char + full pack
    python3 tools/build_shijima.py Blue Green   # build specific ones
"""
import os, sys, shutil, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARS = ["Blue", "Orange", "Yellow", "Green"]
OUT_DIR = os.path.join(ROOT, "dist", "shijima")


def is_useful(fn):
    if fn.startswith(".") or fn.endswith("~"):
        return False
    if fn in ("Thumbs.db", "Desktop.ini", ".DS_Store"):
        return False
    return True


def build_one_zip(char, out_dir):
    """Create a Shijima-Qt-importable zip for one character.

    Layout inside zip:
        Blue/
        ├── img/
        │   ├── stand01.png
        │   ├── walk01.png
        │   └── ...
        ├── actions.xml
        └── behaviors.xml
    """
    src_dir = os.path.join(ROOT, "AVA Shimejis", char)
    if not os.path.isdir(src_dir):
        print(f"  WARNING: {src_dir} not found, skipping")
        return None

    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"AvA_{char}.zip")

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Images go into char/img/
        for fn in sorted(os.listdir(src_dir)):
            if fn.endswith(".png") and is_useful(fn):
                abs_path = os.path.join(src_dir, fn)
                arc_name = os.path.join(char, "img", fn)
                zf.write(abs_path, arc_name)
                count += 1

        # XML files go into char/ (top level, NOT conf/)
        for xml_name in ("actions.xml", "behaviors.xml"):
            xml_path = os.path.join(src_dir, "conf", xml_name)
            if os.path.exists(xml_path):
                arc_name = os.path.join(char, xml_name)
                zf.write(xml_path, arc_name)
                count += 1

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"  {char}: {zip_path} ({count} files, {size_kb:.0f} KB)")
    return zip_path


def build_full_pack_zip(characters, out_dir):
    """Create one zip with all characters in Shijima-Qt DefaultMascot layout.

    Structure:
        img/Blue/stand01.png ...
        actions.xml      (Blue's, at top level for Shijima-ee compat)
        behaviors.xml
    """
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, "AvA_Stick_Pack.zip")

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for char in characters:
            src_dir = os.path.join(ROOT, "AVA Shimejis", char)
            if not os.path.isdir(src_dir):
                continue

            # Images into Blue/img/
            for fn in sorted(os.listdir(src_dir)):
                if fn.endswith(".png") and is_useful(fn):
                    abs_path = os.path.join(src_dir, fn)
                    arc_name = os.path.join(char, "img", fn)
                    zf.write(abs_path, arc_name)
                    count += 1

            # XML at character top level (Blue/actions.xml, Blue/behaviors.xml)
            for xml_name in ("actions.xml", "behaviors.xml"):
                xml_path = os.path.join(src_dir, "conf", xml_name)
                if os.path.exists(xml_path):
                    arc_name = os.path.join(char, xml_name)
                    zf.write(xml_path, arc_name)
                    count += 1

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"  Full pack: {zip_path} ({count} files, {size_kb:.0f} KB)")
    return zip_path


def main():
    all_mode = "--all" in sys.argv
    pack_mode = "--pack" in sys.argv or all_mode
    chars = [a for a in sys.argv[1:] if not a.startswith("-")] or CHARS

    for c in chars:
        if c not in CHARS:
            print(f"Unknown character: {c} (expected {', '.join(CHARS)})")
            return 1

    print(f"Building Shijima-Qt zip packs -> {OUT_DIR}/\n")
    built = []

    for char in chars:
        path = build_one_zip(char, OUT_DIR)
        if path:
            built.append(path)

    if pack_mode:
        print()
        path = build_full_pack_zip(chars, OUT_DIR)
        if path:
            built.append(path)

    if built:
        print(f"\n{'='*50}")
        print(f"Done! {len(built)} zip(s) ready.\n")
        print("IMPORT INTO SHIJIMA-QT:")
        print("  1. Open Shijima-Qt")
        print("  2. Drag & drop any zip into the app window")
        print("  3. Click 'Add' to spawn them\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())