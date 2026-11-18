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
        with patch.object(m, 'engine_pids', side_effect=[[100], [100], [100], [], [], []]), \
             patch.object(m.os, 'kill') as kill, patch.object(m.time, 'sleep') as sleep:
            self.assertTrue(m.stop_engines())
            kill.assert_called_once_with(100, signal.SIGTERM)
            sleep.assert_called_once()

    def test_bounded_kill_escalation_reports_failure_if_still_present(self):
        with patch.object(m, 'engine_pids', return_value=[100]), \
             patch.object(m.os, 'kill') as kill, \
             patch.object(m.time, 'monotonic', side_effect=[0, 9, 10, 13]):
            self.assertFalse(m.stop_engines())
            self.assertEqual(kill.call_args_list[0].args, (100, signal.SIGTERM))
            self.assertEqual(kill.call_args_list[1].args, (100, signal.SIGKILL))


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
                with patch.object(m, 'engine_pids', side_effect=lambda: scan(jar=jar)):
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
                 patch.object(m.subprocess, 'Popen', return_value=child) as launch:
                self.assertEqual(m.manager(), 0)
                self.assertEqual(launch.call_count, 3)
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


if __name__ == '__main__':
    unittest.main()
