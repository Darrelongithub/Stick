#!/usr/bin/env python3
"""Compile the real ShimeLinux playback core with headless test adapters.

This is a verification harness, not the production installer. It compiles the
upstream action/animation/config/environment/image classes plus the patched
Manager/Mascot/UserBehavior/TurnCoordinator/StationaryIdle. Only the desktop
shell, native window, debug window and Nashorn evaluator are replaced.

Usage:
  python3 linux/shimelinux/harness/build_subset.py \
      --upstream /path/to/shimelinux \
      --kotlinc /path/to/kotlinc --java /path/to/java
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PIN = (ROOT / "linux/shimelinux/UPSTREAM_COMMIT").read_text().strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--kotlinc", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "build/shimelinux-harness")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    out = args.out.resolve()
    head = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN:
        raise SystemExit(f"upstream HEAD {head} != pinned {PIN}")
    src = upstream / "src/main/kotlin/com/group_finity/mascot"
    if not (src / "TurnCoordinator.kt").exists():
        raise SystemExit("apply linux/shimelinux/shimelinux-turns.patch to the upstream checkout first")
    if out.exists():
        shutil.rmtree(out)
    kotlin = out / "src"
    kotlin.mkdir(parents=True)
    copied = 0
    for folder in ("action", "animation", "config", "environment", "exception",
                   "hotspot", "image", "script", "sound"):
        for file in (src / folder).glob("*.kt"):
            if file.name in ("Script.kt", "ScriptFilter.kt"):
                continue
            dest = kotlin / file.relative_to(upstream / "src/main/kotlin")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, dest)
            copied += 1
    for rel in ("Mascot.kt", "Manager.kt", "TurnCoordinator.kt",
                "behavior/Behavior.kt", "behavior/UserBehavior.kt",
                "behavior/StationaryIdle.kt"):
        file = src / rel
        dest = kotlin / file.relative_to(upstream / "src/main/kotlin")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, dest)
        copied += 1
    # Two harness-only edits avoid probing a display server. All border/action
    # semantics remain the upstream source copied above.
    env = kotlin / "com/group_finity/mascot/environment/Environment.kt"
    text = env.read_text()
    text = text.replace("Rectangle(Point(0, 0), Toolkit.getDefaultToolkit().screenSize)",
                        "Rectangle(0, 0, 1920, 1080)")
    text = text.replace("timer(daemon = true, period = 5000) { updateScreenRect() }",
                        "// headless harness ticks the environment explicitly")
    env.write_text(text)
    for adapter in ("Adapters.kt", "ScriptBridge.kt"):
        shutil.copyfile(HERE / adapter, kotlin / adapter)
    java_sources = list((upstream / "src/main/java").rglob("*.java"))
    kotlinc = args.kotlinc.resolve()
    java = args.java.resolve()
    env_vars = dict(os.environ, JAVA_HOME=str(java.parent.parent))
    core_jar = out / "shimelinux-core.jar"
    files = [str(p) for p in kotlin.rglob("*.kt")] + [str(p) for p in java_sources]
    print(f"compiling {copied} upstream Kotlin files + {len(java_sources)} Java references", flush=True)
    subprocess.run([str(kotlinc), *files, "-d", str(core_jar), "-nowarn"],
                   env=env_vars, check=True)
    harness_jar = out / "host-harness.jar"
    subprocess.run([str(kotlinc), str(ROOT / "linux/shimelinux/HostPlaybackHarness.kt"),
                    "-cp", str(core_jar), "-d", str(harness_jar), "-nowarn"],
                   env=env_vars, check=True)
    stdlib = kotlinc.parent.parent / "lib/kotlin-stdlib.jar"
    resources = upstream / "src/main/resources"
    print("CORE_JAR=" + str(core_jar))
    print("HARNESS_JAR=" + str(harness_jar))
    print("RUN_CLASSPATH=" + os.pathsep.join(map(str, [harness_jar, core_jar, stdlib, resources])))
    print("JAVA=" + str(java))
    return 0


if __name__ == "__main__":
    sys.exit(main())
