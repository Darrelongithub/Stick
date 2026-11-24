"""Lifecycle regressions without launching Java or requiring a compositor."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import sys
import fcntl
from unittest.mock import MagicMock
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manager', ROOT/'linux/shimelinux-manager.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FullscreenTests(unittest.TestCase):
    def test_clear_visible_workspace(self):
        self.assertIs(m.fullscreen_state([{'activeWorkspace': {'id': 1}}],
                                         [{'id': 1, 'hasfullscreen': False}], []), False)

    def test_other_monitor_and_special_workspace(self):
        monitors = [{'activeWorkspace': {'id': 1}},
                    {'activeWorkspace': {'id': 2}, 'specialWorkspace': {'id': -99}}]
        for workspace in (2, -99):
            states = [{'id': i, 'hasfullscreen': i == workspace} for i in (1, 2, -99)]
            self.assertIs(m.fullscreen_state(monitors, states, []), True)

    def test_client_fullscreen_even_if_workspace_snapshot_lags(self):
        self.assertTrue(m.fullscreen_state([{'activeWorkspace': {'id': 1}}],
                        [{'id': 1, 'hasfullscreen': False}],
                        [{'workspace': {'id': 1}, 'fullscreen': 2}]))

    def test_invisible_fullscreen_does_not_hide_visible_desktop(self):
        self.assertIs(m.fullscreen_state([{'activeWorkspace': {'id': 1}}],
                     [{'id': 1, 'hasfullscreen': False}, {'id': 2, 'hasfullscreen': True}],
                     [{'workspace': {'id': 2}, 'fullscreen': 2}]), False)

    def test_unknown_is_not_treated_as_clear(self):
        for monitors, workspaces, clients in [([], [], []), ([{}], [], []),
            ([{'activeWorkspace': {'id': 1}}], [], []),
            ([{'activeWorkspace': {'id': 1}}], [{'id': 1, 'hasfullscreen': 'false'}], [])]:
            self.assertIsNone(m.fullscreen_state(monitors, workspaces, clients))

    def test_failed_or_malformed_queries_fail_closed(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('hyprctl', 2),
                      subprocess.CalledProcessError(1, 'hyprctl')):
            with patch.object(m.subprocess, 'run', side_effect=error):
                self.assertIsNone(m.query_fullscreen())
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'invalid JSON')):
            self.assertIsNone(m.query_fullscreen())


    def test_queries_share_one_two_second_budget(self):
        values = [
            [{'activeWorkspace': {'id': 1}}],
            [{'id': 1, 'hasfullscreen': False}], []]
        replies = [subprocess.CompletedProcess([], 0, json.dumps(v)) for v in values]
        with patch.object(m.time, 'monotonic', side_effect=[0, 0, .8, 1.7]), \
             patch.object(m.subprocess, 'run', side_effect=replies) as run:
            self.assertIs(m.query_fullscreen(), False)
            for call, expected in zip(run.call_args_list, [2, 1.2, .3]):
                self.assertAlmostEqual(call.kwargs['timeout'], expected)

    def test_expired_snapshot_does_not_issue_more_compositor_requests(self):
        reply = subprocess.CompletedProcess([], 0, '[]')
        with patch.object(m.time, 'monotonic', side_effect=[0, 0, 2.1]), \
             patch.object(m.subprocess, 'run', return_value=reply) as run:
            self.assertIsNone(m.query_fullscreen())
            self.assertEqual(run.call_count, 1)


class LifecycleTests(unittest.TestCase):
    def test_clear_hysteresis_and_restart_cooldown(self):
        policy = m.Policy()
        self.assertFalse(policy.allow(False, 0))
        self.assertFalse(policy.allow(False, 2))
        self.assertTrue(policy.allow(False, 3))
        policy.last_launch = 3
        self.assertFalse(policy.allow(True, 4))
        self.assertFalse(policy.allow(False, 5))
        self.assertFalse(policy.allow(False, 8))
        self.assertTrue(policy.allow(False, 33))
        self.assertFalse(policy.allow(None, 34))
        self.assertFalse(policy.allow(False, 35))

    def test_exact_engine_match_not_unrelated_java(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            for pid, args in [(1, ['/usr/bin/java', '-jar', str(m.JAR)]),
                              (2, ['/usr/bin/java', '-jar', '/tmp/shimelinux.jar.backup']),
                              (3, ['/usr/bin/echo', '-jar', str(m.JAR)]),
                              (4, ['/usr/bin/java', '-jar', '/tmp/unrelated.jar'])]:
                path = proc/str(pid)
                path.mkdir()
                (path/'cmdline').write_bytes(('\0'.join(args)+'\0').encode())
            self.assertEqual(m.engine_pids(proc), [1])

    def test_stop_waits_until_exit_before_success(self):
        running = [True]
        with patch.object(m, 'engine_pids', side_effect=[[100], []]) as scan, \
             patch.object(m, 'process_identity', side_effect=lambda pid: (pid, '123') if running[0] else None), \
             patch.object(m, 'shutdown_snapshot') as snapshot, \
             patch.object(m.os, 'kill') as kill, \
             patch.object(m.time, 'sleep', side_effect=lambda _: running.__setitem__(0, False)) as sleep:
            self.assertTrue(m.stop_engines())
            kill.assert_called_once_with(100, signal.SIGTERM)
            sleep.assert_called_once()
            self.assertEqual(scan.call_count, 2)
            self.assertEqual([c.args[0] for c in snapshot.call_args_list], ['before-term', 'after'])

    def test_bounded_kill_escalation_reports_failure_if_still_present(self):
        with patch.object(m, 'engine_pids', return_value=[100]) as scan, \
             patch.object(m, 'process_identity', return_value=(100, '123')), \
             patch.object(m, 'shutdown_snapshot'), \
             patch.object(m.os, 'kill') as kill, \
             patch.object(m.time, 'monotonic', side_effect=[0, 0, 9, 10, 13, 14]):
            self.assertFalse(m.stop_engines())
            self.assertEqual(kill.call_args_list[0].args, (100, signal.SIGTERM))
            self.assertEqual(kill.call_args_list[1].args, (100, signal.SIGKILL))
            self.assertEqual(scan.call_count, 2)


    def test_real_process_that_ignores_term_is_killed_and_verified(self):
        # Fake Java command line, but Python executable: exercises /proc and
        # real signals without loading ShimeLinux or touching the compositor.
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory)/'fake-engine.jar'
            child = subprocess.Popen(['java', '-c',
                'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("ready",flush=True); time.sleep(60)',
                '-jar', str(jar)], executable=sys.executable, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                scan = m.engine_pids
                with patch.object(m, 'engine_pids', side_effect=lambda: scan(jar=jar)), \
                     patch.object(m, 'shutdown_snapshot'):
                    self.assertIn(child.pid, m.engine_pids())
                    self.assertTrue(m.stop_engines(timeout=.1))
                child.wait(timeout=3)
                self.assertEqual(child.returncode, -signal.SIGKILL)
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait()
                child.stdout.close()


    def test_installer_backs_up_launchers_and_does_not_enable_autostart(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            binaries = home/'.local/bin'
            binaries.mkdir(parents=True)
            for name in ('shimeji', 'shimeji-watchd'):
                (binaries/name).write_text('# old launcher\n')
            env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home/'state'))
            installed = subprocess.run(['bash', str(ROOT/'linux/install-shimelinux-manager.sh')],
                                       env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            state = home/'state/stick-shimelinux'
            self.assertTrue((state/'disabled').exists())
            backups = list(state.glob('launcher-backup-*/shimeji'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), '# old launcher\n')
            self.assertFalse((home/'.config/autostart/ava-shimeji.desktop').exists())
            status = subprocess.run(['bash', str(binaries/'shimeji'), 'status'], env=env,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn('disabled: True', status.stdout)
            # Reinstall immediately: preserve the original backup, don't
            # overwrite it with the replacement launcher's contents.
            again = subprocess.run(['bash', str(ROOT/'linux/install-shimelinux-manager.sh')],
                                   env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(len(list(state.glob('launcher-backup-*/shimeji'))), 2)
            self.assertEqual(backups[0].read_text(), '# old launcher\n')

    def test_disabled_manager_never_queries_or_launches_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state/'disabled').touch()
            with patch.object(m, 'STATE', state), patch.object(m, 'stop_engines', return_value=True), \
                 patch.object(m.signal, 'signal'), patch.object(m, 'query_fullscreen') as query, \
                 patch.object(m.subprocess, 'Popen') as launch:
                self.assertEqual(m.manager(), 0)
                query.assert_not_called()
                launch.assert_not_called()


class ReviewRegressionTests(unittest.TestCase):
    def test_crash_loop_budget_expires_and_recovers_with_time(self):
        policy = m.Policy()
        self.assertFalse(policy.note_exit(0))
        self.assertFalse(policy.note_exit(31))
        self.assertTrue(policy.note_exit(62))
        self.assertFalse(policy.note_exit(400))

    def manager_context(self, state):
        jar = state/'fake.jar'
        jar.touch()
        event = MagicMock()
        event.is_set.return_value = False
        return jar, event

    def test_repeated_engine_exit_disables_instead_of_restarting_forever(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            jar, event = self.manager_context(state)
            child = MagicMock(pid=123)
            child.poll.return_value = 1
            with patch.object(m, 'STATE', state), patch.object(m, 'JAR', jar), \
                 patch.object(m.threading, 'Event', return_value=event), \
                 patch.object(m.signal, 'signal'), patch.object(m, 'engine_pids', return_value=[]), \
                 patch.object(m, 'query_fullscreen', return_value=False), \
                 patch.object(m.Policy, 'allow', return_value=True), \
                 patch.object(m, 'display_ready', return_value=(True, 'ready')), \
                 patch.object(m.subprocess, 'Popen', return_value=child) as launch:
                self.assertEqual(m.manager(), 0)
                self.assertEqual(launch.call_count, 3)
                self.assertNotIn('-XX:+UseSerialGC', launch.call_args.args[0])
                self.assertEqual(launch.call_args.kwargs['stdout'], subprocess.PIPE)
                self.assertTrue((state/'disabled').exists())

    def test_incomplete_shutdown_disables_and_does_not_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            jar, event = self.manager_context(state)
            with patch.object(m, 'STATE', state), patch.object(m, 'JAR', jar), \
                 patch.object(m.threading, 'Event', return_value=event), \
                 patch.object(m.signal, 'signal'), patch.object(m, 'engine_pids', return_value=[123]), \
                 patch.object(m, 'query_fullscreen', return_value=True), \
                 patch.object(m, 'stop_engines', return_value=False), \
                 patch.object(m.subprocess, 'Popen') as launch:
                self.assertEqual(m.manager(), 0)
                launch.assert_not_called()
                self.assertTrue((state/'disabled').exists())

    def test_spawn_failure_is_logged_and_disables_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            jar, event = self.manager_context(state)
            with patch.object(m, 'STATE', state), patch.object(m, 'JAR', jar), \
                 patch.object(m.threading, 'Event', return_value=event), \
                 patch.object(m.signal, 'signal'), patch.object(m, 'engine_pids', return_value=[]), \
                 patch.object(m, 'query_fullscreen', return_value=False), \
                 patch.object(m.Policy, 'allow', return_value=True), \
                 patch.object(m, 'display_ready', return_value=(True, 'ready')), \
                 patch.object(m.subprocess, 'Popen', side_effect=FileNotFoundError('java')):
                with self.assertLogs(m.LOG, level='ERROR') as logs:
                    self.assertEqual(m.manager(), 1)
                self.assertIn('Manager failed', '\n'.join(logs.output))
                self.assertTrue((state/'disabled').exists())
                self.assertFalse((state/'manager.pid').exists())

    def test_start_waits_for_whole_stop_transaction_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            lock = (state/'command.lock').open('w')
            fcntl.flock(lock, fcntl.LOCK_EX)
            worker = """import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('m', sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.STATE=Path(sys.argv[2])
m.control=lambda command:(m.STATE/'entered').write_text(command)
m.locked_control('start')
"""
            process = subprocess.Popen([sys.executable, '-c', worker,
                                        str(ROOT/'linux/shimelinux-manager.py'), str(state)])
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.wait(timeout=.2)
                self.assertFalse((state/'entered').exists())
                fcntl.flock(lock, fcntl.LOCK_UN)
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertEqual((state/'entered').read_text(), 'start')
            finally:
                lock.close()
                if process.poll() is None:
                    process.kill()
                process.wait()

    def test_installer_process_scan_failure_cannot_replace_launchers(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bin_dir = home/'bin'
            bin_dir.mkdir()
            python = bin_dir/'python3'
            python.write_text('#!/bin/sh\nexit 2\n')
            python.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=str(bin_dir)+':'+os.environ['PATH'])
            installed = subprocess.run(['bash', str(ROOT/'linux/install-shimelinux-manager.sh')],
                                       env=env, text=True, capture_output=True, timeout=10)
            self.assertNotEqual(installed.returncode, 0)
            self.assertIn('Could not inspect', installed.stderr)
            self.assertFalse((home/'.local/bin/shimeji').exists())


class ShutdownLagTests(unittest.TestCase):
    def test_reused_pid_is_not_signalled(self):
        with patch.object(m, 'engine_pids', side_effect=[[100], [100]]), \
             patch.object(m, 'process_identity', side_effect=[(100, 'old')]+[(100, 'new')]*5), \
             patch.object(m, 'shutdown_snapshot'), patch.object(m.os, 'kill') as kill:
            self.assertFalse(m.stop_engines())
            kill.assert_not_called()

    def test_identity_uses_start_time_and_ignores_zombies(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc/'100').mkdir()
            stat = proc/'100/stat'
            for state in ('S', 'D', 'Z', 'X'):
                stat.write_text('100 (java worker) '+state+' '+'0 '*18+'456 0 0')
                identity = m.process_identity(100, proc)
                self.assertEqual(identity, None if state in ('Z', 'X') else (100, '456'))

    def test_snapshots_are_bounded_private_and_passive(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m, 'STATE', Path(directory)), patch.object(m.os, 'kill') as kill:
                for stage in ('before-term', 'before-kill', 'after'):
                    m.shutdown_snapshot(stage, [os.getpid()])
                    m.shutdown_snapshot(stage, [os.getpid()])
                paths = list(Path(directory).glob('shutdown-*.json'))
                self.assertEqual(len(paths), 3)
                for path in paths:
                    data = json.loads(path.read_text())
                    self.assertIn('pressure/io', data['system'])
                    self.assertIn(str(os.getpid()), data['processes'])
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                kill.assert_not_called()


class DisplayPreflightTests(unittest.TestCase):
    def test_missing_display_does_not_even_invoke_native_probe(self):
        with patch.dict(os.environ, {'DISPLAY': ''}), patch.object(m.subprocess, 'run') as run:
            ready, reason = m.display_ready()
            self.assertFalse(ready)
            self.assertIn('DISPLAY', reason)
            run.assert_not_called()

    def test_probe_uses_inherited_auth_and_timeout(self):
        with patch.dict(os.environ, {'DISPLAY': ':7', 'XAUTHORITY': '/tmp/test-auth'}), \
             patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            self.assertTrue(m.display_ready()[0])
            self.assertEqual(run.call_args.kwargs['timeout'], 2)
            self.assertNotIn('env', run.call_args.kwargs)
            self.assertEqual(run.call_args.args[0][0], sys.executable)

    def test_native_probe_failure_and_timeout_stay_off(self):
        with patch.dict(os.environ, {'DISPLAY': ':7'}):
            for code in (1, 2, -6):
                with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, '', '')):
                    self.assertFalse(m.display_ready()[0])
            with patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 2)):
                self.assertFalse(m.display_ready()[0])

    def test_display_retry_is_throttled_and_recovers(self):
        gate = m.DisplayGate()
        with patch.object(m, 'display_ready', side_effect=[(False, 'no display'), (True, 'ready')]) as probe:
            self.assertFalse(gate.allow(0))
            self.assertFalse(gate.allow(1))
            self.assertFalse(gate.allow(4.9))
            self.assertTrue(gate.allow(5))
            self.assertEqual(probe.call_count, 2)

    def test_missing_display_never_launches_java(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            jar = state/'fake.jar'
            jar.touch()
            event = MagicMock()
            event.is_set.side_effect = [False, True]
            with patch.object(m, 'STATE', state), patch.object(m, 'JAR', jar), \
                 patch.object(m.threading, 'Event', return_value=event), \
                 patch.object(m.signal, 'signal'), patch.object(m, 'engine_pids', return_value=[]), \
                 patch.object(m, 'query_fullscreen', return_value=False), \
                 patch.object(m.Policy, 'allow', return_value=True), \
                 patch.object(m, 'display_ready', return_value=(False, 'no display')), \
                 patch.object(m.subprocess, 'Popen') as launch:
                self.assertEqual(m.manager(), 0)
                launch.assert_not_called()
                self.assertFalse((state/'disabled').exists())


class FinalReviewTests(unittest.TestCase):
    def test_fullscreen_change_during_display_probe_prevents_launch(self):
        for changed_state in (True, None):
            with self.subTest(fullscreen=changed_state), tempfile.TemporaryDirectory() as directory:
                state = Path(directory)
                jar = state/'fake.jar'
                jar.touch()
                event = MagicMock()
                event.is_set.side_effect = [False, True]
                with patch.object(m, 'STATE', state), patch.object(m, 'JAR', jar), \
                     patch.object(m.threading, 'Event', return_value=event), \
                     patch.object(m.signal, 'signal'), patch.object(m, 'engine_pids', return_value=[]), \
                     patch.object(m, 'query_fullscreen', side_effect=[False, changed_state]), \
                     patch.object(m.Policy, 'allow', return_value=True), \
                     patch.object(m, 'display_ready', return_value=(True, 'ready')), \
                     patch.object(m.subprocess, 'Popen') as launch:
                    self.assertEqual(m.manager(), 0)
                    launch.assert_not_called()

    def test_native_probe_disables_its_own_core_dumps(self):
        # Run only the prefix before ctypes work; do not touch a real display.
        prefix = m.X11_PROBE.split('try:', 1)[0]
        checked = subprocess.run([sys.executable, '-c', prefix+
            '\nassert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)'],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(checked.returncode, 0, checked.stderr)


class EngineLogTests(unittest.TestCase):
    def run_writer(self, state, count, limit=1024):
        child = subprocess.Popen([sys.executable, '-c',
            f'import os; os.write(1, b"x" * {count})'], stdout=subprocess.PIPE)
        with patch.object(m, 'STATE', state):
            reader = m.capture_engine_output(child, limit)
            try:
                self.assertEqual(child.wait(timeout=10), 0)
                reader.join(timeout=5)
                self.assertFalse(reader.is_alive())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
        return sorted(state.glob('engine.log*'))

    def test_long_unbroken_output_is_bounded_during_one_engine_run(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            files = self.run_writer(state, 250_000)
            self.assertEqual(len(files), 3)
            self.assertTrue(all(0 < f.stat().st_size <= 1024 for f in files))

    def test_legacy_append_only_log_is_trimmed_before_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state/'engine.log').write_bytes(b'z' * 50_000)
            files = self.run_writer(state, 40)
            self.assertTrue(all(f.stat().st_size <= 1024 for f in files))
            self.assertEqual((state/'engine.log.1').read_bytes(), b'z' * 1024)
            self.assertEqual((state/'engine.log').read_bytes(), b'x' * 40)

    def test_output_is_drained_even_when_log_cannot_be_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'missing'
            with self.assertLogs(m.LOG, level='ERROR') as logs:
                self.run_writer(state, 250_000)
            self.assertEqual(len(logs.output), 1)

    def test_small_output_is_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            self.run_writer(state, 400)
            self.assertEqual((state/'engine.log').read_bytes(), b'x' * 400)


class StartupInventoryTests(unittest.TestCase):
    def put(self, config, relative, text):
        path = config/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_multiple_launchers_are_reported_without_running_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            self.put(config, 'autostart/ava.desktop',
                     '[Desktop Entry]\nExec=/home/user/.local/bin/shimeji start\n')
            self.put(config, 'hypr/extra/pets.conf',
                     '# exec-once = shimelinux\nexec-once = /opt/ava-toggle.sh --start\n')
            self.put(config, 'systemd/user/ava-runner.service',
                     '[Service]\nExecStart=python3 /opt/ava_runner.py\n')
            wants = config/'systemd/user/default.target.wants'
            wants.mkdir()
            (wants/'ava-runner.service').symlink_to('../ava-runner.service')
            with patch.object(m.subprocess, 'run') as run, \
                 patch.object(m.subprocess, 'Popen') as launch:
                found = m.startup_inventory(config)
            run.assert_not_called()
            launch.assert_not_called()
            self.assertEqual({f['kind'] for f in found}, {
                'xdg-autostart', 'hyprland-exec', 'systemd-unit', 'systemd-enabled-reference'})
            self.assertEqual(len(found), 4)
            self.assertEqual(next(f['line'] for f in found if f['kind'] == 'hyprland-exec'), 2)

    def test_hidden_desktop_is_distinguished_and_values_are_not_interpolated(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            self.put(config, 'autostart/pets.desktop',
                     '[Desktop Entry]\nExec=shimelinux %u\nHidden=true\n')
            self.assertEqual(m.startup_inventory(config)[0]['state'], 'disabled')

    def test_comments_and_unrelated_entries_do_not_count(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            self.put(config, 'hypr/hyprland.conf',
                     '# exec-once = shimeji start\nexec-once = terminal # shimeji\n')
            self.put(config, 'systemd/user/editor.service',
                     '# ExecStart=shimelinux\nExecStart=/usr/bin/editor\nDescription=shimeji\n')
            self.assertEqual(m.startup_inventory(config), [])

    def test_large_and_malformed_files_do_not_look_like_a_clean_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            self.put(config, 'hypr/huge.conf', 'x' * 65537)
            self.put(config, 'autostart/broken.desktop', 'not a desktop entry')
            found = m.startup_inventory(config)
            self.assertEqual(len(found), 2)
            self.assertTrue(all(f['kind'] == 'unreadable' for f in found))

    def test_special_file_is_not_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config/'hypr').mkdir()
            os.mkfifo(config/'hypr/blocked.conf')
            self.assertEqual(m.startup_inventory(config)[0]['reason'], 'not a regular file')

    def test_scan_limit_and_missing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            self.assertEqual(m.startup_inventory(config/'absent'), [])
            self.put(config, 'hypr/one.conf', 'exec-once = shimelinux')
            self.put(config, 'hypr/two.conf', 'exec-once = shimelinux')
            self.assertEqual(m.startup_inventory(config, max_files=1)[-1]['kind'], 'incomplete')

    def test_audit_does_not_create_state_or_execute_probes(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            state = home/'state'
            env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home/'config'),
                       XDG_STATE_HOME=str(state))
            result = subprocess.run([sys.executable, str(ROOT/'linux/shimelinux-manager.py'), 'audit'],
                                    env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('read-only', result.stdout)
            self.assertFalse(state.exists())


if __name__ == '__main__':
    unittest.main()
