# Additional slowdown audit

Scope: repository launchers and ShimeLinux upstream v1.4.0, the version previously
recovered for the laptop. This sandbox has neither the installed laptop JAR nor
a live Hyprland session. Source findings do not prove a whole-desktop freeze.
Artwork and autostart configuration are unchanged.

## 1. High-frequency compositor subprocesses inside the engine (unfixed here)

Pinned upstream commit: `f07823c84f75dd46fb72a8c5544da1413692d41a` (v1.4.0).

- [Manager.kt, start and tick](https://github.com/BujjuIsABee/shimelinux/blob/f07823c84f75dd46fb72a8c5544da1413692d41a/src/main/kotlin/com/group_finity/mascot/Manager.kt#L70-L105): a 40 ms timer invokes `environment.tick()` before updating/painting mascots.
- [WaylandEnvironment.kt, tick](https://github.com/BujjuIsABee/shimelinux/blob/f07823c84f75dd46fb72a8c5544da1413692d41a/src/main/kotlin/io/github/bujjuisabee/shimelinux/wayland/WaylandEnvironment.kt#L55-L90): Hyprland cursor position comes from `execute("hyprctl", "cursorpos")` every tick.
- [Utils.kt, execute](https://github.com/BujjuIsABee/shimelinux/blob/f07823c84f75dd46fb72a8c5544da1413692d41a/src/main/kotlin/com/group_finity/mascot/Utils.kt#L63-L70): starts a process, calls `waitFor()` without a timeout, then reads stdout. It does not drain stderr.

At the nominal timer rate, this means about **25 process launches and synchronous
compositor requests per second per engine**, in addition to the watchdog's
queries. It is one environment query per tick, not per character. Slow requests
reduce the effective rate; this is not a measured rate from the laptop.

A stalled cursor query can stall the animation timer indefinitely. Repeated
process creation and compositor IPC are real architectural overhead. They may
contribute to desktop load but are not proof that this path caused a Hyprland
freeze. A cursor reply is normally tiny, so the utility's general pipe-deadlock
risk (waiting before reading a large stdout/stderr response) is not established
as a trigger for this particular command.

The same cursorpos/waitFor pattern was also present in upstream main when
inspected. Do not assume an upgrade alone removes it.

### Correct engine-level repair

Cache cursor position and update it asynchronously with at most one outstanding
request, a short timeout, and stale-last-good fallback. Prefer a supported native
input/IPC mechanism rather than forking a command every animation tick. Drain
output while the child runs, bound captured bytes, and terminate/reap timed-out
children. Close the worker during engine shutdown. Test compositor stalls,
invalid replies, shutdown while a request is pending, and cursor interactions.
Do not disable cursor interactions or change desktop detection to bypass the
problem: those approaches change behavior rather than repair it.

That repair requires building/testing the ShimeLinux engine. This repository
ships the character pack and wrapper, not these Kotlin engine sources; no
untested replacement JAR or PATH interception shim has been installed.

## 2. Snapshot timeouts multiplied shutdown latency (fixed in this branch)

The watchdog issued three sequential `hyprctl` commands, each allowed two
seconds. Three slow but successful replies could therefore spend almost six
seconds in one snapshot. SIGTERM only sets an event; the Python manager can
remain inside that snapshot before reaching shutdown. This makes the stop
command feel slow precisely when compositor IPC is already sluggish.

The three calls now share **one nominal two-second deadline**. No later command
is issued after the budget expires; an incomplete snapshot still fails closed.
This does not reduce the number of queries on a healthy desktop and does not
promise a hard real-time bound on process creation or kernel scheduling.
Regression tests cover decreasing per-call budgets and refusing further IPC
after deadline exhaustion.

## 3. Reinitialization cost remains on fullscreen transitions

The manager intentionally terminates Java to hide native mascot windows. When
fullscreen ends, it creates a new JVM and reloads the selected packs. The
three-second clear-state gate and 30-second launch cooldown limit restart
frequency; they do not eliminate this reload cost. A fast hide/show feature
would need engine support, rather than SIGSTOP (which can freeze native clients
while holding resources) or new compositor rules with unverified semantics.

## 4. Other entry points can create competing load (installation-dependent)

`linux/hyprland.sh` and `linux/ava-toggle.sh` launch the older Shimeji-ee engine;
`runner/install-service.sh` installs a separate Qt runner with unlimited systemd
restart attempts every three seconds. These are not the actual ShimeLinux
manager. Their existence in this repository does not show that they are enabled
on the laptop. If previously installed and still enabled, they can add load
outside this manager's singleton and crash budget. Do not automatically delete
user startup entries or stop unrelated Java processes based on this suspicion.

## Status

Earlier branch fixes remove forced Serial GC and bound live console logging.
The additional shared snapshot deadline is tested locally. Engine cursor-query
repair, laptop startup-provider inventory, and attribution of the whole-desktop
freeze remain open. No merge, deployment, or deliberate laptop freeze test was
performed for this audit.

## 5. Eager pixel caches and duplicate image names

Further pinned v1.4.0 sources:

- [AnimationBuilder.kt](https://github.com/BujjuIsABee/shimelinux/blob/f07823c84f75dd46fb72a8c5544da1413692d41a/src/main/kotlin/com/group_finity/mascot/config/AnimationBuilder.kt#L67-L78) loads poses in its initializer; `loadPose` calls `ImagePairLoader.load`.
- [ImagePairLoader.kt](https://github.com/BujjuIsABee/shimelinux/blob/f07823c84f75dd46fb72a8c5544da1413692d41a/src/main/kotlin/com/group_finity/mascot/image/ImagePairLoader.kt#L49-L68) makes both directions and caches by image paths, not pixel contents.
- [WaylandNativeImage.kt](https://github.com/BujjuIsABee/shimelinux/blob/f07823c84f75dd46fb72a8c5544da1413692d41a/src/main/kotlin/io/github/bujjuisabee/shimelinux/wayland/WaylandNativeImage.kt#L34-L39) retains the pixels in an `IntArray`.

The current repository actions reference 2,097 distinct PNG paths across the four
characters (no explicit right-image attributes). At 1x, 48,302,208 source pixels
x 4 bytes x 2 directions is **368.52 MiB** of pixel-array payload. That excludes
array/object headers, scripts, JVM/runtime memory, native window buffers,
temporary decoded/scaled/flipped images and GC headroom. It is not a measured
live heap/RSS figure, nor evidence of a leak. At larger scale, pixel storage
increases roughly with the square of the scale factor.

`tools/deduplicate_image_refs.py` builds a separate offline copy of the pack. It
only changes `Pose Image` paths when RGBA pixels, dimensions and the single
unambiguous anchor are identical. It skips explicit right-image pairs,
ambiguous anchors, symlink images and non-leaf paths. All PNG files are copied
unchanged; timing, pose count, ordering, other attributes and behaviors remain
unchanged. Source files and the installed pack are never edited. Existing output
directories are refused instead of overwritten.

| Character | Redundant paths shared | Estimated pixel payload saved at 1x |
| --- | ---: | ---: |
| Blue | 112 | 17.73 MiB |
| Orange | 145 | 24.17 MiB |
| Yellow | 55 | 10.74 MiB |
| Green | 63 | 12.23 MiB |
| Total | 375 | 64.88 MiB |

Build in an isolated directory (requires Pillow in the Python environment):

```bash
python3 tools/deduplicate_image_refs.py 'AVA Shimejis' --output preview/optimized-pack
```

This does **not** install the copy or start Java. Do not copy XML into a running
engine. The optimization does not remove the remaining eager loading, cursor
query hot path, native GTK startup failure risk or prove a freeze resolved.
Tests compare every pose's non-image attributes and every changed reference's
RGBA pixels against the source, and cover idempotence, ambiguous anchors,
explicit right images, comments, source preservation and output-path refusal.

## Read-only startup inventory

The manager now supports `audit`, also forwarded by the installed `shimeji`
wrapper. From this checkout it can be run without installation:

```bash
python3 linux/shimelinux-manager.py audit
```

It lists mascot-related commands in user XDG desktop entries, Hyprland `.conf`
snippets and systemd user units/`.wants` references. It distinguishes disabled XDG
entries, returns file/line hints without raw command strings, and never runs the
configured commands, probes the display or creates manager state/log files.
It reads at most 256 matched files and 64 KiB per file, reports truncation/read
errors, and skips special files rather than blocking on a FIFO. Unrelated and
commented-out commands are ignored.

**Configured is not running:** unsourced Hyprland snippets and disabled systemd
units may appear. This is not a complete startup resolver: custom config paths,
shell scripts, system-wide entries and live service state are outside its scope.
No startup entries are disabled or changed.
