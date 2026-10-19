#!/usr/bin/env python3
"""Disable multiplication in installed packs/settings, not just the repo copy.

Call only after the host app has exited: both hosts can save their in-memory
settings over changes made while they are running. Keep the first backup and
preserve unrelated settings, comments and CRLF line endings.
"""
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET

CHARS = ("Blue", "Orange", "Yellow", "Green")


def read(path):
    return path.read_bytes().decode("utf-8", errors="surrogateescape") if path.exists() else ""


def save(path, text):
    data = text.encode("utf-8", errors="surrogateescape")
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".ava-bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_bytes(data)


def properties(text, values):
    """Replace ALL occurrences: java.util.Properties uses the last duplicate."""
    eol = "\r\n" if "\r\n" in text else "\n"
    out, seen = [], set()
    for line in text.splitlines():
        m = re.match(r"^[ \t]*([^#!\s=:]+)(?:[ \t]*[=:]|[ \t]+|$)", line)
        key = m[1] if m else None
        if key not in values:
            out.append(line)
        elif key not in seen:
            out.append(f"{key}={values[key]}")
            seen.add(key)
    out.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
    return eol.join(out) + eol


def configure_shimeji(target):
    settings = target / "conf/settings.properties"
    save(settings, properties(read(settings), {
        "Breeding": "false", "ActiveShimeji": "/".join(CHARS),
    }))
    # hyprland.sh is also used without reinstalling the art. Repair old installed
    # copies too: a zero-frequency behaviour can still be picked by libshijima.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from patch_xml import disable_breeding
    for char in CHARS:
        for name in ("actions.xml", "behaviors.xml"):
            path = target / "img" / char / "conf" / name
            if path.exists():
                patched = disable_breeding(read(path))
                ET.fromstring(patched)  # never write malformed XML
                save(path, patched)
    print("  Breeding=false; one each of Blue/Orange/Yellow/Green; installed cloning actions removed")


def configure_shijima(path):
    # QSettings("pixelomer", "Shijima-Qt") stores this in [General]. Do not
    # reserialize the whole file: Qt has its own escaping for other values.
    # Upstream Windowed mode is a live QAction, NOT a persisted setting or an
    # HTTP API option. Adding a made-up windowedMode=false key would do nothing;
    # the running app's Settings -> Windowed mode checkbox must be unchecked.
    text = read(path)
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    out, general, found = [], False, False
    for line in lines:
        if line.strip().startswith("["):
            if general and not found:
                out.append("multiplicationEnabled=false")
                found = True
            general = line.strip() == "[General]"
        if general and re.match(r"\s*multiplicationEnabled\s*=", line):
            if not found:
                out.append("multiplicationEnabled=false")
                found = True
        else:
            out.append(line)
    if not found:
        if not general:
            out.extend(["", "[General]"])
        out.append("multiplicationEnabled=false")
    save(path, eol.join(out).lstrip("\r\n") + eol)
    print(f"  multiplicationEnabled=false ({path})")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("shimeji", "shijima"):
        sys.exit("Usage: configure-mascots.py shimeji FOLDER | shijima SETTINGS_FILE")
    if sys.argv[1] == "shimeji":
        configure_shimeji(Path(sys.argv[2]))
    else:
        configure_shijima(Path(sys.argv[2]))


if __name__ == "__main__":
    main()
