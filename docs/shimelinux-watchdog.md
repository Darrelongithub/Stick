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

Keep mascot autostart disabled during diagnosis. Save work first. Do not attempt
another deliberate fullscreen freeze to validate this patch.

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
- `engine.log`: engine stdout/stderr, including load/configuration errors. This
  file is appended and is not rotated while Java has it open; inspect its size
  periodically. It cannot guarantee capturing the final event in a hard freeze.

```bash
state="${XDG_STATE_HOME:-$HOME/.local/state}/stick-shimelinux"
tail -n 60 "$state/manager.log"
tail -n 40 "$state/engine.log"
```

## Rollback

Stop and verify exit with the NEW launcher before restoring any backup. Copy the
backed-up `shimeji` and `shimeji-watchd` files from the recorded backup directory
to `~/.local/bin/`. Keep autostart disabled; restoration does not start anything.

## Verification

100 unit tests pass, including 19 manager tests. These cover query failures,
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

Remaining limits: `engine.log` is still an append-only engine stream, so it can
grow during prolonged use; it is not covered by manager-log rotation. Explicitly
launching the engine outside the manager bypasses launch locking. No automated
unit test here establishes that a fullscreen transition is safe on the user's
GPU/compositor. Keep autostart disabled during diagnosis.
