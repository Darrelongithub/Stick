import contextlib
import fcntl
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shijima_session", ROOT / "linux/shijima-session.py")
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class ShijimaSessionTests(unittest.TestCase):
    def test_reconciles_existing_crowd_and_repeated_runs_without_touching_other_mascots(self):
        state = [{"id": 1, "name": "Blue"}, {"id": 2, "name": "Blue"},
                 {"id": 3, "name": "Orange"}, {"id": 4, "name": "Another pack"}]
        changes = []

        def api(method, path, body=None):
            if method == "GET":
                return {"mascots": state.copy()}
            changes.append((method, path, body))
            if method == "POST":
                state.append({"id": max(m["id"] for m in state) + 1, "name": body["name"]})
            if method == "DELETE":
                state[:] = [m for m in state if m["id"] != int(path.rsplit("/", 1)[1])]
            return {}

        with patch.object(session, "call", side_effect=api), patch.object(session.subprocess, "Popen") as launch:
            session.start(["shijima-qt"])
            first = changes.copy()
            session.start(["shijima-qt"])
            launch.assert_not_called()
        self.assertEqual(first, changes)
        self.assertEqual(len(changes), 3)  # one duplicate removed, two missing spawned
        self.assertIn(("DELETE", "/mascots/2", None), changes)
        self.assertEqual(sorted(m["name"] for m in state),
                         sorted([*session.WANT, "Another pack"]))

    def test_malformed_api_is_not_an_empty_screen(self):
        for response in ({}, [], {"mascots": None}, {"mascots": [{}]},
                         {"mascots": [{"name": "Blue", "id": "1"}]},
                         {"mascots": [{"name": "Blue", "id": 1}, {"name": "Blue", "id": 1}]}):
            with self.subTest(response=response), patch.object(session, "call", return_value=response) as api, \
                    patch.object(session.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError):
                    session.start(["shijima-qt"])
                self.assertEqual(api.call_count, 1)
                launch.assert_not_called()

    def test_network_start_waits_for_api_forces_xcb_and_closes_lock_fds(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_CACHE_HOME": folder}), \
                patch.object(session, "on_screen", side_effect=[urllib.error.URLError("offline"), []]), \
                patch.object(session, "call", return_value={}) as api, \
                patch.object(session.subprocess, "Popen") as launch:
            session.start(["shijima-qt"])
            self.assertEqual(launch.call_count, 1)
            self.assertTrue(launch.call_args.kwargs["close_fds"])
            self.assertEqual(launch.call_args.kwargs["env"]["QT_QPA_PLATFORM"], "xcb")
            self.assertEqual([c.args[2]["name"] for c in api.call_args_list], list(session.WANT))

    def test_http_error_does_not_launch_another_app(self):
        error = urllib.error.HTTPError(session.API, 500, "failure", {}, None)
        with patch.object(session, "on_screen", side_effect=error), \
                patch.object(session.subprocess, "Popen") as launch:
            with self.assertRaises(urllib.error.HTTPError):
                session.start(["shijima-qt"])
            launch.assert_not_called()

    def test_lock_prevents_overlapping_helpers(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_RUNTIME_DIR": folder}):
            state = Path(folder) / "ava-shimeji"
            state.mkdir()
            with (state / "shijima-session.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with patch.object(session, "start") as start:
                    self.assertEqual(session.main(["--", "shijima-qt"]), 0)
                    start.assert_not_called()

    def test_failed_spawn_is_an_error_not_silent_success(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_RUNTIME_DIR": folder}), \
                patch.object(session, "start", side_effect=OSError("failed to spawn")), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(session.main(["--", "shijima-qt"]), 1)
            self.assertIn("failed to spawn", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
