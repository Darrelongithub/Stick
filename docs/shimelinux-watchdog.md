# ShimeLinux: bounded shutdown and conservative fullscreen handling

This replaces the user's custom `shimeji` / `shimeji-watchd` scripts, not the
animation pack or the ShimeLinux engine. It is specific to Hyprland and the
installed JAR at `/usr/share/java/shimelinux.jar`.

## Evidence and limits

The old stop command sent TERM and immediately printed success; Java was briefly
still present and subsequently exited. That establishes delayed shutdown, not
an unkillable engine. The old fullscreen detector returned false on query errors,
looked at only the active workspace, and revived Java without a launch cooldown.
Those are concrete lifecycle weaknesses corrected here. The reported desktop
freeze is NOT reproduced in this sandbox and its root cause remains unproven.
This patch must not be described as a confirmed GPU/kernel freeze fix.

## Behavior

- One manager per user, protected by a file lock. A command lock serializes
  complete start/stop transactions; a separate launch gate serializes engine
  creation against stop's persistent disabled marker.
- Three unexpected engine exits within five minutes disable automatic restarts.
  An explicit `shimeji start` is required to try again. Intentional fullscreen
  shutdowns do not consume this failure budget.
- An incomplete shutdown or manager exception also disables automatic launches;
  fatal exceptions are recorded with traceback in the manager log.
- Check workspaces/clients on every visible monitor, including special
  workspaces. Nonzero client fullscreen is conservatively treated as hide.
- Hyprland command failure, timeout, incomplete or malformed data means UNKNOWN:
  stop the engine and never start it based on that result.
- Three continuous clear seconds before startup; at least 30 seconds between
  launches. No desktop socket event storm can launch overlapping Java instances.
- Stop waits up to eight seconds after TERM, then uses KILL and verifies exit for
  another two seconds. If a process remains (for example in uninterruptible
  kernel sleep), stop reports failure rather than falsely claiming success.
- If a manager is running, manual stop first disables future launches, asks the
  manager to terminate and waits up to 18 seconds before reporting a manager
  shutdown timeout. It never blindly kills an unrelated reused manager PID.
- Match same-user Java command lines with the exact `-jar` path. No broad
  `pkill java` or substring matches against arbitrary shell commands.
- Retain the user's private Java 21 selection when available. No speculative heap
  or graphics flags are imposed. Engine exit/start requires loading assets again;
  this does not optimize the Java engine's memory or rendering implementation.

Fullscreen disappearance is not instantaneous: one-second polling, query time
and engine shutdown can introduce delay. Unknown state intentionally keeps pets
off. Rapid fullscreen toggling may keep them off until the cooldown expires.
The stop timeout is NOT evidence of or a cure for a compositor freeze.

## Installation (after this change is available locally)

Save work first. Do not attempt another deliberate fullscreen freeze to validate
this patch. The installer leaves your existing autostart choice unchanged.

1. With the OLD launcher, `shimeji stop` and allow it time to finish.
2. Confirm neither the old watcher nor the engine is running. The installer also
   checks exact process arguments and refuses to replace an active launcher.
3. From the updated repository:

```bash
bash linux/install-shimelinux-manager.sh
shimeji status
shimeji diagnose
```

The installer backs up both launchers under
`${XDG_STATE_HOME:-$HOME/.local/state}/stick-shimelinux/launcher-backup-*`.
It installs new scripts but **does not start the engine, enable autostart, or
change the character packs**. Requires Python 3 and Hyprland's `hyprctl`; no pip
packages or sudo needed. Do not run the manager under sudo.

Only after reviewing diagnostics and choosing to resume ordinary use:

```bash
shimeji start
shimeji status
# Later:
shimeji stop
```

`start` requests startup; `status` verifies actual processes. Do not additionally
run `/usr/bin/shimelinux` or the tray launcher. That bypasses this manager.

## Logs

Under `${XDG_STATE_HOME:-$HOME/.local/state}/stick-shimelinux/`:

- `manager.log` (rotates at 2 MiB, retains two backups): state changes, query
  failures, engine starts, shutdown escalation and remaining processes.
- `engine.log`: engine stdout/stderr, including load/configuration errors. Rotates
  during a single engine run at 2 MiB, retaining two backups (6 MiB total). A legacy
  oversized current log is trimmed to its last 2 MiB on first new output. It cannot
  guarantee capturing the final event in a hard freeze.

```bash
state="${XDG_STATE_HOME:-$HOME/.local/state}/stick-shimelinux"
tail -n 60 "$state/manager.log"
tail -n 40 "$state/engine.log"
```

## Rollback

Stop and verify exit with the NEW launcher before restoring any backup. Copy the
backed-up `shimeji` and `shimeji-watchd` files from the recorded backup directory
to `~/.local/bin/`. Restoration does not start anything or change autostart.

## Verification

110 unit tests pass, including 29 manager tests. These cover query failures,
multiple visible monitors, special workspaces, cooldown, persistent disable,
exact engine matching, bounded TERM/KILL and truthful failure reporting. A real
Python subprocess with a Java-shaped argument list deliberately ignores TERM;
the test verifies KILL and exit, without launching the real engine/compositor.
An isolated-HOME installer test verifies backups, initial disabled state and
absence of autostart modification. Shell syntax checks pass. No live Hyprland
or user-laptop freeze reproduction is claimed.


## Bug-scan follow-up

The first implementation passed 94 tests but missed several lifecycle bugs.
The follow-up adds regressions and corrections for:

1. **Start/stop race:** start could clear the disable marker while stop was still
   waiting for exit. A whole-command lock now spans the stop transaction.
2. **Infinite failed-launch retries:** a 30-second cooldown was not a failure
   limit. Repeated unexpected exits now trip a persistent disabled state.
3. **Shutdown timeout followed by later revival:** failed cleanup previously
   returned to polling and could eventually launch again. It now disables/exits.
4. **Silent background failure:** spawn/manager exceptions were lost because
   the daemon's stderr is detached. They now get a logged traceback and disable.
5. **Installer scan error treated as absence:** shell `if` conflated scanner
   errors with the no-process result. Busy, clear and error results are now
   separate; errors abort before launcher changes. Missing Python also aborts.
6. **Backup overwrite within one second:** timestamp-only paths could collide.
   `mktemp` suffixes preserve independent backups on immediate reinstalls.

The extra tests include a real cross-process command-lock contention check,
crash-loop manager iterations, failed shutdown, a simulated spawn error,
installer scan-error refusal, and immediate-reinstall backup preservation.
The process scanner also recognizes a manager launched directly from this repo.

Remaining limits: explicitly launching the engine outside the manager bypasses
launch locking. No automated unit test here establishes that a fullscreen
transition is safe on the user's GPU/compositor.


## Shutdown lag follow-up: targeted waits and passive diagnostics

The user's fullscreen hide succeeded once, but manual stop still caused reported
whole-desktop lag. That earlier success does not establish resolution. Do not
ask the user to deliberately reproduce another freeze to validate this change.

Previously, waiting for TERM/KILL called `engine_pids()` repeatedly: every
100 milliseconds it enumerated all of `/proc` and opened command lines for the
user's processes. The new shutdown transaction enumerates all processes only
at its beginning and end. In between, it checks the selected Java PIDs and
kernel start times, treating zombies as exited. It does not signal a PID whose
start time changed. This reduces watchdog work during shutdown; it is NOT proof
that the full scans caused a desktop stall. A narrow check-to-signal PID race
still exists without pidfd-based signalling; start-time checks reduce but do
not eliminate it.

New fixed-size-count, passive diagnostic files in the state directory:

- `shutdown-before-term.json`: written before signalling Java.
- `shutdown-before-kill.json`: written only if TERM times out.
- `shutdown-after.json`: remaining matching PIDs and post-wait system state.

Each contains uptime/clock timestamps, memory totals, CPU/memory/I/O pressure,
and available Java status, process stat, wait channel and I/O counters. Files
are mode 0600 and overwritten per stage, not created per poll. They may contain
stale data from an earlier attempt: compare timestamps. No thread-dump signals,
forced garbage collection, GPU commands, full filesystem scans or forced disk
sync are used. Read failures are recorded where possible. They cannot guarantee
survival of a forced power cut. The manager log also records elapsed shutdown
seconds and the final PID list.

The TERM (8s) and post-KILL (2s) wait limits are unchanged. A waiting terminal
command and an unresponsive entire desktop are different observations; the
bounded wait alone does not explain loss of pointer/input across the session.
No new claim is made about Java shutdown-hook or compositor behavior.

Before installing this follow-up, collect the EXISTING log without starting or
stopping the engine again:

```bash
state="${XDG_STATE_HOME:-$HOME/.local/state}/stick-shimelinux"
tail -n 100 "$state/manager.log"
```

New regressions check only two global scans per shutdown, PID reuse detection,
zombie handling, and private bounded passive snapshots. The existing real
subprocess test still verifies TERM/KILL escalation without loading ShimeLinux.


## Confirmed tray abort and X11 readiness guard

The matching saved Java abort (PID 2127, Nov 18) contains GTK style/widget
creation through JNA. Engine log context identifies:

```
Main createTrayIcon Creating the tray icon
Gtk-ERROR: Can't create a GtkStyleContext without a display connection
```

This establishes the native abort site, not a causal explanation for every
whole-desktop freeze or manual-stop lag. A transient missing X11 display,
authorization failure, or tray/toolkit initialization problem can require
additional differentiation. No graphics driver or global GTK configuration
change follows from this evidence alone.

Before every managed Java launch, a separate bounded Python process now calls
`XOpenDisplay` and `XCloseDisplay` against the inherited session environment.
Hyprland responding on Wayland alone no longer authorizes an X11-dependent
engine launch. Missing DISPLAY, unavailable libX11, failed authorization,
probe crash or a two-second timeout means Java stays off. Failed probes retry
at most once every five seconds and log reason changes, without creating an
engine/core dump to test readiness. `shimeji diagnose` reports the result too.

No hard-coded DISPLAY=:0, guessed XAUTHORITY path, xhost permission changes,
new pip requirement, tray-disabling flag, or launch from a text console is used.
Fedora's system libX11.so.6 is required for the probe (already used by the engine
in the supplied core report). DISPLAY/XAUTHORITY are inherited, not copied from
another user or session. Start from the same graphical-session terminal used by
other X11 apps. The manager does not rewrite its inherited environment if a
session is replaced; leave it off and start deliberately in the new session.

**Limit:** a successful X11 connection probe does not prove GTK/JNA tray init
will succeed later, particularly if the display disappears while assets load.
Repeated unexpected engine exits still disable restarts after three failures
within five minutes. We have not reproduced this exact GTK abort or the user's
compositor freeze in a live native session. Do not claim the guard conclusively
fixes either, or request another deliberate freeze as validation.

Five new tests exercise missing DISPLAY, inherited authentication, native-probe
exit/timeout failure, retry throttling/recovery and manager refusal to launch
without a verified connection. Native calls are isolated/mocked; none launch
the real engine or manipulate the user's display.


### Final pre-merge scan

The final review also closes the stale-fullscreen-snapshot window around the
X11 preflight: fullscreen is checked again after probing and before the launch
gate. Fullscreen or unknown state aborts that launch. This is still polling,
not an atomic compositor transaction; state can always change immediately after
a check. The restart cooldown is timestamped at actual successful process
creation rather than before potentially slow preflight calls.

The isolated native probe sets its own core-dump limit to zero. If Xlib itself
aborts, retries cannot generate new probe core dumps. This does not change
Java's core-dump policy or erase existing diagnostic evidence. Regression tests
verify both the changed-state launch refusal and the probe's core limit.


## Slowdown audit: garbage collection and continuous logging

The launcher previously forced `-XX:+UseSerialGC`. Serial GC performs collection
with one worker and stops Java application threads during collection. This was
not justified by measurements on this laptop; the launcher now lets Java 21
choose its default collector. This may reduce mascot pauses but is not evidence
that garbage collection froze Hyprland, and does not impose a heap cap.

The engine console was redirected to an append-only file. Upstream logs behavior
changes at INFO level, making that file grow for as long as pets run. A bounded
reader now drains stdout/stderr in at most 8 KiB chunks and rotates files during
a running Java process, not just on restart. It does not accumulate whole lines
in memory. If storage fails, it logs the failure once and continues draining and
discarding output rather than blocking Java on a full stdout pipe. It never
waits for the log reader during shutdown. The oldest console diagnostics can be
overwritten; save relevant excerpts before a long session.

Still unresolved: polling issues three Hyprland queries and scans processes per
second; fullscreen hiding intentionally exits Java, so returning reloads assets;
other launchers can bypass the manager. These are overhead/race risks, not
confirmed explanations for a whole-desktop stall. The native GTK tray abort
previously identified remains a separate concern: the display preflight cannot
guarantee that later tray initialization succeeds.

Autostart remains the user's choice and is not disabled by this fix. Bare
Hyprland does not itself process XDG autostart desktop entries: check whether the
session already runs an autostart provider (for example UWSM) before relying on
one. Do not add a second direct engine launcher alongside the manager.

## Further scan: engine IPC and shutdown latency

See [the additional performance audit](shimelinux-performance-audit.md) for pinned
ShimeLinux 1.4.0 source references. Its animation timer synchronously launches
`hyprctl cursorpos` at a nominal 25 Hz and waits without a timeout; this engine
hot path is separate from the manager's polling and is not fixed by this wrapper.

The manager's three-command fullscreen snapshot now shares one nominal two-second
budget instead of allowing two seconds per command. This limits IPC-related
stop latency during slow replies while preserving fail-closed behavior.

A read-only `shimeji audit` command now inventories potential user startup
conflicts without display queries, service commands, state/log writes or changes
to autostart. See the performance audit for scope and limits. The audit also
explains the optional offline image-reference deduplicator: it preserves all
pixels and animation semantics while sharing identical frames in the engine's
path-keyed cache. Neither the manager installer nor this audit installs a new
character pack automatically.
