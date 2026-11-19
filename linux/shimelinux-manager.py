#!/usr/bin/env python3
"""Conservative ShimeLinux/Hyprland lifecycle manager. Python stdlib only."""
import argparse
import fcntl
import glob
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME/'.local/state'))/'stick-shimelinux'
JAR = Path('/usr/share/java/shimelinux.jar')
LOG = logging.getLogger('shimelinux-manager')


def engine_pids(proc=Path('/proc'), jar=JAR):
    """Match exact -jar argument, never a substring in an unrelated command."""
    matches = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            args = (entry/'cmdline').read_bytes().decode().split('\0')
            index = args.index('-jar')
            if Path(args[index+1]) == jar and Path(args[0]).name == 'java':
                matches.append(int(entry.name))
        except (OSError, ValueError, IndexError, UnicodeError):
            continue
    return matches


def fullscreen_state(monitors, workspaces, clients):
    """True=hide, False=clear, None=unknown (also hide).

    Inspect every visible monitor, including special workspaces. Missing fields
    and malformed output must not turn an unknown state into permission to run.
    """
    if not monitors or not isinstance(workspaces, list) or not isinstance(clients, list):
        return None
    visible = set()
    try:
        for monitor in monitors:
            if monitor.get('disabled', False):
                continue
            visible.add(monitor['activeWorkspace']['id'])
            special = monitor.get('specialWorkspace', {}).get('id', 0)
            if special:
                visible.add(special)
        if not visible:
            return None
        states = {w['id']: w['hasfullscreen'] for w in workspaces if w['id'] in visible}
        if any(not isinstance(value, bool) for value in states.values()):
            return None
        if any(states.values()):
            return True
        for client in clients:
            if client.get('workspace', {}).get('id') in visible:
                value = client.get('fullscreen')
                if isinstance(value, bool) or not isinstance(value, int):
                    return None
                if value != 0:
                    return True
        return False if visible.issubset(states) else None
    except (KeyError, TypeError, AttributeError):
        return None


def query_fullscreen():
    try:
        result = []
        for name in ('monitors', 'workspaces', 'clients'):
            command = subprocess.run(['hyprctl', '-j', name], capture_output=True,
                                     text=True, timeout=2, check=True)
            value = json.loads(command.stdout)
            if not isinstance(value, list):
                return None
            result.append(value)
        return fullscreen_state(*result)
    except (OSError, subprocess.SubprocessError, ValueError):
        LOG.warning('Hyprland query failed; mascots will remain off')
        return None


def process_identity(pid, proc=Path('/proc')):
    """PID plus kernel start time; zombies have already finished shutdown."""
    try:
        fields = (proc/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] in ('Z', 'X') else (pid, fields[19])
    except (OSError, IndexError):
        return None


def shutdown_snapshot(stage, pids):
    """Small bounded passive snapshot; no Java signals, GC or disk sync.

    Best effort: a forced power loss can still lose buffered writes. These
    three fixed filenames bound storage rather than create files per poll.
    """
    try:
        data = {'stage': stage, 'wall_time': time.time(), 'monotonic': time.monotonic(),
                'processes': {}, 'system': {}}
        for filename in ('meminfo', 'pressure/cpu', 'pressure/memory', 'pressure/io'):
            try:
                data['system'][filename] = Path('/proc', filename).read_text()[:8192]
            except OSError as error:
                data['system'][filename] = str(error)
        for pid in pids:
            record = {}
            for filename in ('status', 'stat', 'wchan', 'io'):
                try:
                    record[filename] = Path(f'/proc/{pid}/{filename}').read_text()[:8192]
                except OSError as error:
                    record[filename] = str(error)
            data['processes'][str(pid)] = record
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = STATE/f'shutdown-{stage}.json'
        with path.open('w') as output:
            os.chmod(path, 0o600)
            json.dump(data, output, indent=2)
    except OSError:
        LOG.warning('Could not write shutdown snapshot', exc_info=True)


def stop_engines(timeout=8):
    """Bounded TERM/KILL with targeted waits, not a full /proc scan per tick."""
    pids = engine_pids()
    if not pids:
        return True
    began = time.monotonic()
    targets = [identity for pid in pids if (identity := process_identity(pid))]
    shutdown_snapshot('before-term', pids)

    def alive():
        return [identity for identity in targets if process_identity(identity[0]) == identity]

    def send(sig):
        for pid, _ in alive():
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

    def wait(seconds):
        deadline = time.monotonic()+seconds
        while alive() and time.monotonic() < deadline:
            time.sleep(.1)

    LOG.info('Requesting engine shutdown: pids=%s', pids)
    send(signal.SIGTERM)
    wait(timeout)
    if alive():
        LOG.warning('Engine did not exit within %ss; sending SIGKILL', timeout)
        shutdown_snapshot('before-kill', [pid for pid, _ in alive()])
        send(signal.SIGKILL)
        wait(2)
    # A final global scan detects externally launched/replacement processes,
    # without adopting or signalling them during this shutdown transaction.
    remaining = engine_pids()
    shutdown_snapshot('after', remaining)
    LOG.info('Shutdown verification: elapsed=%.3fs remaining=%s', time.monotonic()-began, remaining)
    if remaining:
        LOG.error('Engine still present: %s; no replacement will be launched', remaining)
    return not remaining


# Run native X11 probing in a separate process. A stuck/crashing native call
# must not take the watchdog with it. Uses the same inherited DISPLAY and
# XAUTHORITY as Java; no guessed :0 or hard-coded authentication file.
X11_PROBE = """import ctypes, resource, sys
# A native probe crash must not produce core dumps in a retry loop.
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
try:
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int
    display = x11.XOpenDisplay(None)
    if not display:
        print('XOpenDisplay failed: check Xwayland and session authentication', file=sys.stderr)
        sys.exit(1)
    x11.XCloseDisplay(display)
except OSError:
    print('Could not load the system X11 library', file=sys.stderr)
    sys.exit(2)
"""


def display_ready():
    if not os.environ.get('DISPLAY', '').strip():
        return False, 'DISPLAY is unset; start from the graphical session, not a text console'
    try:
        result = subprocess.run([sys.executable, '-c', X11_PROBE],
                                capture_output=True, text=True, timeout=2)
        if result.returncode:
            return False, f'X11 connection probe failed (exit {result.returncode})'
        return True, 'X11 connection verified'
    except (OSError, subprocess.SubprocessError):
        return False, 'X11 connection probe could not complete within its limit'


class DisplayGate:
    def __init__(self):
        self.next_attempt = 0
        self.last_reason = None

    def allow(self, now):
        if now < self.next_attempt:
            return False
        ready, reason = display_ready()
        if reason != self.last_reason:
            LOG.info('Display preflight: %s', reason)
            self.last_reason = reason
        # Failed readiness is not an engine failure: keep Java OFF and retry
        # gently, without generating GTK aborts or core dumps to test readiness.
        self.next_attempt = now + 5 if not ready else 0
        return ready


def java_bin():
    candidates = sorted(glob.glob(str(HOME/'shimelinux-java21.*/bin/java')))
    return candidates[-1] if candidates else 'java'


class Policy:
    """Require sustained clear state and cooldown; hide immediately on doubt."""
    def __init__(self):
        self.clear_since = None
        self.last_launch = None
        self.unexpected_exits = []

    def note_exit(self, now):
        self.unexpected_exits = [t for t in self.unexpected_exits if now-t <= 300]
        self.unexpected_exits.append(now)
        return len(self.unexpected_exits) >= 3

    def allow(self, state, now):
        if state is not False:
            self.clear_since = None
            return False
        if self.clear_since is None:
            self.clear_since = now
        return (now-self.clear_since >= 3 and
                (self.last_launch is None or now-self.last_launch >= 30))


def manager():
    lock = (STATE/'manager.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return 0
    (STATE/'manager.pid').write_text(str(os.getpid()))
    end = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: end.set())
    signal.signal(signal.SIGINT, lambda *_: end.set())
    policy = Policy()
    display_gate = DisplayGate()
    child = None
    previous = 'initial'
    try:
        while not end.is_set() and not (STATE/'disabled').exists():
            if child is not None:
                code = child.poll()
                if code is not None:
                    LOG.warning('Engine exited unexpectedly: pid=%s status=%s', child.pid, code)
                    child = None
                    if policy.note_exit(time.monotonic()):
                        LOG.error('Three unexpected exits in five minutes; disabling restarts')
                        (STATE/'disabled').touch()
                        break
            state = query_fullscreen()
            now = time.monotonic()
            ready = policy.allow(state, now)
            if state != previous:
                LOG.info('Fullscreen state=%s (None means unknown/off)', state)
                previous = state
            pids = engine_pids()
            if state is not False or len(pids) > 1:
                if pids:
                    if not stop_engines():
                        (STATE/'disabled').touch()
                        break
                    if child is not None:
                        child.poll()
                        child = None  # Requested hide is not an unexpected exit.
                    policy.clear_since = None
            elif ready and not pids:
                if not display_gate.allow(now):
                    end.wait(1)
                    continue
                # Opening X11 may start Xwayland and take time. Do not use
                # the fullscreen snapshot taken before that readiness probe.
                launch_state = query_fullscreen()
                if launch_state is not False:
                    policy.allow(launch_state, time.monotonic())
                    end.wait(1)
                    continue
                # Serialize launch with the stop command's disable marker.
                with (STATE/'gate.lock').open('w') as gate:
                    fcntl.flock(gate, fcntl.LOCK_EX)
                    if end.is_set() or (STATE/'disabled').exists():
                        break
                    if not JAR.is_file():
                        LOG.error('Missing %s; disabling manager', JAR)
                        (STATE/'disabled').touch()
                        break
                    env = dict(os.environ, GDK_BACKEND='x11', _JAVA_AWT_WM_NONREPARENTING='1')
                    with (STATE/'engine.log').open('ab') as output:
                        child = subprocess.Popen([java_bin(), '-XX:+UseSerialGC', '-jar', str(JAR)],
                                                 env=env, cwd=HOME, stdout=output,
                                                 stderr=subprocess.STDOUT, start_new_session=True)
                    policy.last_launch = time.monotonic()
                    LOG.info('Launched engine pid=%s', child.pid)
            end.wait(1)
    except Exception:
        LOG.exception('Manager failed; disabling automatic launches')
        (STATE/'disabled').touch()
        return 1
    finally:
        try:
            if not stop_engines():
                (STATE/'disabled').touch()
            if child:
                child.poll()
        finally:
            (STATE/'manager.pid').unlink(missing_ok=True)
            LOG.info('Manager exited')
            lock.close()
    return 0


def manager_pid():
    try:
        pid = int((STATE/'manager.pid').read_text())
        args = Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0')
        return pid if str(Path(__file__).resolve()) in args and 'run' in args else None
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'stop', 'status', 'run', 'diagnose'])
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    logging.basicConfig(handlers=[RotatingFileHandler(STATE/'manager.log', maxBytes=2*1024*1024, backupCount=2)],
                        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.command == 'run':
        return manager()
    if args.command == 'diagnose':
        print('fullscreen:', query_fullscreen(), '(None=unknown; stays off)')
        display_ok, reason = display_ready()
        print('display ready:', display_ok, '-', reason)
        print('engine PIDs:', engine_pids())
        print('logs:', STATE)
        return 0
    if args.command == 'status':
        print('manager:', manager_pid() or 'stopped')
        print('engines:', engine_pids() or 'stopped')
        print('disabled:', (STATE/'disabled').exists())
        print('logs:', STATE)
        return 0
    # Keep an explicit start from clearing stop's disable marker while stop
    # is still waiting for the old manager/engine. The launch gate alone only
    # protects individual writes, not this whole lifecycle transaction.
    return locked_control(args.command)


def locked_control(command):
    with (STATE/'command.lock').open('w') as command_lock:
        fcntl.flock(command_lock, fcntl.LOCK_EX)
        return control(command)


def control(command):
    if command == 'start':
        if not JAR.is_file():
            print(f'Missing {JAR}; not starting', file=sys.stderr)
            return 1
        with (STATE/'gate.lock').open('w') as gate:
            fcntl.flock(gate, fcntl.LOCK_EX)
            (STATE/'disabled').unlink(missing_ok=True)
        if not manager_pid():
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'run'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        print('Start requested; waits for a verified non-fullscreen state. Use shimeji status.')
        return 0
    with (STATE/'gate.lock').open('w') as gate:
        fcntl.flock(gate, fcntl.LOCK_EX)
        (STATE/'disabled').touch()
    pid = manager_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic()+18
        while manager_pid() and time.monotonic() < deadline:
            time.sleep(.1)
        if manager_pid():
            print('Manager has not exited; disabled marker prevents new launches.', file=sys.stderr)
            return 1
    stopped = stop_engines()
    print('Mascots OFF; shutdown verified.' if stopped else 'Shutdown incomplete; inspect logs.')
    return 0 if stopped else 1


if __name__ == '__main__':
    raise SystemExit(main())
