# ShimeLinux global animation turns

This directory contains a source patch for **ShimeLinux** (the Linux/BSD
Shimeji-ee port) that makes the four AvA characters share **one process-wide
animation stage**:

- at most one mascot performs an animation at a time, across all image sets;
- requests are FIFO, including menu actions, drag, throw and fall recovery;
- natural completion is reported only after the final pose has been applied;
- waiting mascots use a stationary idle and never request turns;
- disposal/removal cancels queued and active work explicitly;
- a drag released before its lease starts cannot leave a stuck lease.

The patch is pinned to upstream commit:

```text
b131465f5af478347009bcf6b29bad6f5579af85
```

See `UPSTREAM_COMMIT` and `LICENSE.upstream`.

## Apply to a ShimeLinux checkout

```bash
git clone https://github.com/BujjuIsABee/shimelinux.git ~/src/shimelinux
git -C ~/src/shimelinux checkout b131465f5af478347009bcf6b29bad6f5579af85

python3 linux/shimelinux/install.py --source ~/src/shimelinux
# optional: copy the four image sets into ShimeLinux's user config
python3 linux/shimelinux/install.py --source ~/src/shimelinux \
    --install-pack --activate
```

`install.py` refuses to apply the patch to a different upstream commit or to a
checkout that already contains a modified `TurnCoordinator.kt`. It does not
download a JDK, Gradle, or Maven dependencies. Build the patched checkout with
its own Gradle wrapper when your distribution has JDK 21 and the required build
tools:

```bash
cd ~/src/shimelinux
./gradlew jar
```

The patch touches:

- `Manager.kt`: snapshot ticking list, apply all frames, then acknowledge
  completions and pump the next FIFO request;
- `Mascot.kt`: behavior setter queues work, preserves pending natural
  completions, handles null successors, and cancels unstarted granted drags;
- `behavior/UserBehavior.kt`: reports completion once, after pose/hotspot work;
- `behavior/Behavior.kt`: exposes `behaviorName`;
- `TurnCoordinator.kt`: FIFO leases, explicit complete/cancel, stale-token
  rejection, bounded event log;
- `behavior/StationaryIdle.kt`: one zero-velocity idle pose, no turn requests.

## Headless verification harness

The full ShimeLinux Gradle build needs JDK 21, Gradle, and Maven dependencies.
In sandboxes without those, `harness/build_subset.py` compiles the real upstream
playback core (actions, animation, config, environment, hotspots, images, plus
the patched Manager/Mascot/UserBehavior/TurnCoordinator/StationaryIdle) with
headless test adapters. Only the desktop shell, native window, debug window and
Nashorn evaluator are replaced. Production ShimeLinux still uses Nashorn.

```bash
python3 linux/shimelinux/harness/build_subset.py \
    --upstream ~/src/shimelinux \
    --kotlinc /path/to/kotlinc \
    --java /path/to/java

java -Djava.awt.headless=true \
    -cp build/shimelinux-harness/host-harness.jar:build/shimelinux-harness/shimelinux-core.jar:/path/to/kotlin-stdlib.jar:~/src/shimelinux/src/main/resources \
    HostPlaybackHarnessKt . preview/native
```

The harness loads all four image sets, runs 1200 ticks, exercises drag/release,
a queued drag released before grant, the menu `setBehaviorAll` path, pause, and
disposal, and writes `preview/native/native-events.tsv`, composite frames, and
`summary.txt`. It asserts:

- `overlaps == 0`
- `idleMovement == 0`
- `pauseViolations == 0`
- `completed > 20`
- disposed mascot removed from the manager

Latest local result:

```text
NATIVE CORE: 1200 ticks, 22 completed, 10 cancelled; overlaps=0 idleMovement=0 pauseViolations=0
```

This is a **headless core playback verification**, not a real Hyprland/GNOME
window-manager run. The native window/compositor path still needs an on-desktop
smoke test.
