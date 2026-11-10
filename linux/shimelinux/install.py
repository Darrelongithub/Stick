#!/usr/bin/env python3
"""Apply the AvA turn-coordinator patch to a pinned ShimeLinux source checkout.

This does not download a JDK, Gradle, or Maven dependencies. It applies the
source patch and (optionally) installs the four image sets into ShimeLinux's
per-user config directory. Build/run the patched checkout with its own Gradle
wrapper when your distribution has the required JDK 21 and build tools.

Example:
  python3 linux/shimelinux/install.py --source ~/src/shimelinux --install-pack
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
PIN = (BASE / "UPSTREAM_COMMIT").read_text().strip()
CHARS = ("Blue", "Orange", "Yellow", "Green")


def git(source: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(source), *args], check=check,
                          text=True, capture_output=True)


def apply_patch(source: Path) -> None:
    head = git(source, "rev-parse", "HEAD").stdout.strip()
    if head != PIN:
        raise SystemExit(f"ShimeLinux checkout is {head}, expected {PIN}.\n"
                         "Check out the pinned commit before applying this patch.")
    patch = BASE / "shimelinux-turns.patch"
    marker = source / "src/main/kotlin/com/group_finity/mascot/TurnCoordinator.kt"
    if marker.exists():
        reverse = git(source, "apply", "--reverse", "--check", str(patch), check=False)
        if reverse.returncode != 0:
            raise SystemExit("TurnCoordinator.kt exists but the patch does not reverse cleanly; "
                             "refusing to overwrite a modified host.")
        print("ShimeLinux turn patch already applied.")
        return
    check = git(source, "apply", "--check", str(patch), check=False)
    if check.returncode != 0:
        raise SystemExit("Patch does not apply cleanly:\n" + check.stderr + check.stdout)
    git(source, "apply", str(patch))
    print("Applied ShimeLinux turn patch.")


def install_pack(target: Path, activate: bool) -> None:
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    for char in CHARS:
        src = ROOT / "AVA Shimejis" / char
        dest = target / char
        shutil.copytree(src, dest, dirs_exist_ok=True)
        print(f"installed {char} -> {dest}")
    settings = target.parent / "conf" / "settings.properties"
    settings.parent.mkdir(parents=True, exist_ok=True)
    lines = settings.read_text().splitlines() if settings.exists() else []
    updates = {"Breeding": "false"}
    if activate:
        updates["ActiveShimeji"] = "/".join(CHARS)
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    settings.write_text("\n".join(out) + "\n")
    print(f"updated {settings}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="ShimeLinux git checkout at the pinned commit")
    parser.add_argument("--install-pack", action="store_true",
                        help="copy the four image sets into ShimeLinux's user config")
    parser.add_argument("--pack-target", type=Path,
                        default=Path.home() / ".config/shimelinux/img",
                        help="image-set directory (default: ~/.config/shimelinux/img)")
    parser.add_argument("--activate", action="store_true",
                        help="with --install-pack, set ActiveShimeji to the four AvA characters")
    parser.add_argument("--build", action="store_true",
                        help="run ./gradlew jar in the patched checkout (needs JDK 21/build deps)")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not (source / ".git").exists():
        raise SystemExit(f"{source} is not a git checkout")
    apply_patch(source)
    if args.build:
        subprocess.run(["./gradlew", "jar"], cwd=source, check=True)
    if args.install_pack:
        install_pack(args.pack_target, args.activate)
    print("Done. Restart ShimeLinux so it loads the patched host and XML.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
