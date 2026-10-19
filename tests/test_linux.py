"""Linux integration regressions; no desktop, JVM, Qt or Hyprland required.

Run: python3 -m unittest discover -s tests -v
All HOME/XDG paths and desktop commands are isolated. The fake JVM is a real
process with Java-shaped argv, so locks, /proc matching and shutdown ordering
are exercised, rather than mocked away.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LinuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stick-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.target = self.home / "Shimeji (1) 'crew'"
        self.target.mkdir()
        (self.target / "Shimeji-ee.jar").touch()
        self.config = self.home / "custom-config"
        self.hypr = self.config / "hypr"
        self.hypr.mkdir(parents=True)
        (self.hypr / "hyprland.conf").write_text("# user's config\n")
        self.env = dict(os.environ)
        for key in ("HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY", "DISPLAY", "QT_QPA_PLATFORM"):
            self.env.pop(key, None)
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.config),
                        XDG_DATA_HOME=str(self.home / "data"),
                        XDG_CACHE_HOME=str(self.home / "cache"),
                        XDG_RUNTIME_DIR=str(self.home / "runtime"),
                        XDG_CURRENT_DESKTOP="Hyprland", MOCK_VERSION="0.53.3",
                        JAVA_EVENTS=str(self.home / "java-events"),
                        SHIJIMA_BUILD_DIR=str(self.home / "build"),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"])
        self.script("hyprctl", '''#!/usr/bin/env python3
import json, os, sys
if sys.argv[1] == "version":
    if "-j" in sys.argv:
        print(os.environ.get("MOCK_VERSION_JSON", json.dumps({"tag": "v" + os.environ["MOCK_VERSION"]})))
    else:
        print("Hyprland " + os.environ["MOCK_VERSION"] + " built from branch test")
elif sys.argv[1] == "clients":
    print(os.environ.get("MOCK_CLIENTS", "[]"))
elif sys.argv[1] == "configerrors":
    print(os.environ.get("MOCK_ERRORS", ""), end="")
elif sys.argv[1] == "reload":
    print("ok")
else:
    sys.exit(1)
''')
        self.script("notify-send", "#!/bin/sh\nexit 0\n")
        runtime = self.home / "fake-jvm.py"
        runtime.write_text('''import json, os, signal, sys, time
from pathlib import Path
running = True
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
with open(os.environ["JAVA_EVENTS"], "a") as f:
    f.write(json.dumps({"pid": os.getpid(), "cwd": os.getcwd(), "args": sys.argv[1:]}) + "\\n")
while running:
    time.sleep(0.01)
if os.environ.get("JAVA_SAVE_SETTINGS"):
    Path(os.environ["JAVA_SAVE_SETTINGS"]).write_text("Breeding=true\\nActiveShimeji=Old\\n")
''')
        self.script("java", '#!/usr/bin/env bash\n'
                    'if [ "${1:-}" = -version ]; then echo \'openjdk version "17"\' >&2; exit; fi\n'
                    f'exec -a java python3 {shlex.quote(str(runtime))} "$@"\n')
        shutil.copy2(ROOT / "linux/ava-toggle.sh", self.target / "ava-toggle.sh")
        (self.target / "ava-toggle.sh").chmod(0o755)
        self.addCleanup(self.stop_java)

    def script(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def run_script(self, script, *args, ok=True, env=None):
        result = subprocess.run(["bash", str(script), *map(str, args)],
                                cwd=ROOT, env=env or self.env, text=True,
                                capture_output=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def control(self, *args, **kwargs):
        return self.run_script(self.target / "ava-toggle.sh", *args, **kwargs)

    def stop_java(self):
        self.control("--stop", ok=False)

    def events(self, count=1):
        path = self.home / "java-events"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
            if len(events) >= count:
                return events
            time.sleep(0.02)
        self.fail(f"expected {count} fake JVM starts")

    def repair(self, *args, **kwargs):
        return self.run_script(ROOT / "linux/hyprland.sh", self.target, *args, **kwargs)

    def shijima(self, *args, **kwargs):
        return self.run_script(ROOT / "linux/shijima.sh", *args, **kwargs)

    def assert_rules(self, text, syntax):
        rules = [line for line in text.splitlines() if line.startswith("windowrule")]
        self.assertGreaterEqual(len(rules), 5)
        if syntax == "v3":
            allowed = {"float on", "decorate off", "border_size 0", "no_shadow on",
                       "no_blur on", "no_anim on", "rounding 0", "no_focus on"}
            for rule in rules:
                match, effect = rule.split(" = ", 1)[1].split(", ")
                self.assertTrue(match.startswith("match:class ^("), rule)
                self.assertIn(effect, allowed)
            self.assertNotIn("noborder", text)
        elif syntax == "v2":
            self.assertTrue(all(line.startswith("windowrulev2 = ") and ", class:^(" in line
                                for line in rules))
        else:
            self.assertTrue(all(line.startswith("windowrule = ") and ", ^(" in line
                                for line in rules))
            self.assertNotIn("class:", text)

    def test_version_boundaries_both_installers(self):
        for version, syntax in (("0.29.0", "v1"), ("0.40.0", "v2"), ("0.52.2", "v2"),
                                ("0.53.0", "v3"), ("0.54.1", "v3"), ("0.55.0", "v3")):
            with self.subTest(version=version):
                self.env["MOCK_VERSION"] = version
                self.repair("--no-start")
                self.assert_rules((self.hypr / "ava-shimeji.conf").read_text(), syntax)
                # No --autostart: the rules must still be installed.
                self.shijima("--install")
                text = (self.hypr / "ava-shijima-qt.conf").read_text()
                self.assert_rules(text, syntax)
                self.assertNotIn("no_focus", text)  # manager stays usable
                self.assertNotIn("nofocus", text)

    def test_text_version_fallback_and_unknown_fail_closed(self):
        self.env["MOCK_VERSION_JSON"] = "not JSON"
        self.repair("--no-start")
        self.assert_rules((self.hypr / "ava-shimeji.conf").read_text(), "v3")
        self.env["MOCK_VERSION"] = "unknown"
        result = self.repair("--no-start", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--syntax", result.stderr)
        self.repair("--syntax", "v2", "--no-start")
        self.assert_rules((self.hypr / "ava-shimeji.conf").read_text(), "v2")

    def test_lua_rules_and_autostart_both_installers(self):
        (self.hypr / "hyprland.conf").unlink()
        main = self.hypr / "hyprland.lua"
        main.write_text("-- user's config\n")
        self.env["MOCK_VERSION"] = "0.55.0"
        self.script("shijima-qt", "#!/bin/sh\nexit 0\n")
        for _ in range(2):
            self.repair("--no-start")
            self.shijima("--install", "--autostart")
        for name in ("ava-shimeji", "ava-shijima"):
            text = (self.hypr / (name + ".lua")).read_text()
            self.assertIn("decorate = false", text)
            self.assertIn("border_size = 0", text)
            self.assertNotIn("no_border", text)
            self.assertEqual(text.count('hl.on("hyprland.start"'), 1)
            self.assertEqual(main.read_text().count(f'require("{name}")'), 1)
        self.assertIn("--start", (self.hypr / "ava-shimeji.lua").read_text())
        self.assertEqual((self.hypr / "hyprland.lua.ava-bak").read_text(), "-- user's config\n")
        with main.open("a") as f:
            f.write('hl.exec_cmd("keep-my-edit")\n')
        self.shijima("--uninstall")
        self.repair("--uninstall")
        self.assertIn("keep-my-edit", main.read_text())

    def test_hypr_install_idempotent_uninstall_preserves_edits(self):
        for _ in range(2):
            self.repair("--no-start")
        main = self.hypr / "hyprland.conf"
        self.assertEqual(main.read_text().count("source = "), 1)
        text = (self.hypr / "ava-shimeji.conf").read_text()
        self.assertEqual(text.count("exec-once ="), 1)
        self.assertNotIn("java -jar", text)
        self.assertIn("--start", text)
        self.assertEqual((self.hypr / "hyprland.conf.ava-bak").read_text(), "# user's config\n")
        with main.open("a") as f:
            f.write("# keep subsequent user edit\n")
        self.repair("--uninstall")
        self.assertIn("keep subsequent user edit", main.read_text())
        self.assertNotIn("source =", main.read_text())

    def test_dry_run_and_check_do_not_write_or_spawn(self):
        before = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.repair("--dry-run")
        self.env["MOCK_CLIENTS"] = json.dumps([
            {"class": "com-group_finity-mascot-Main", "initialClass": "com-group_finity-mascot-Main"},
            {"class": "com-group_finity-mascot-Main", "initialClass": "com-group_finity-mascot-Main"},
        ])
        report = self.repair("--check")
        self.assertIn("live shimeji windows: 2", report.stdout)
        self.assertNotIn("SyntaxError", report.stderr)
        after = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_config_errors_prevent_start(self):
        self.env["MOCK_ERRORS"] = "Config error: invalid rule\n"
        result = self.repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid rule", result.stderr)
        self.assertFalse((self.home / "java-events").exists())
        self.assertNotIn("Done.", result.stdout)

    def test_simultaneous_start_is_idempotent_restart_and_stop(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.control("--start"), range(8)))
        self.assertEqual(sum("Shimejis started" in r.stdout for r in results), 1)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(len(self.control("--status").stdout.splitlines()), 1)
        self.control("--restart")
        self.assertEqual(len(self.events(2)), 2)
        self.control("--stop")
        self.assertEqual(self.control("--status", ok=False).returncode, 1)
        self.control("--stop")

    def test_relative_jar_detected_and_settings_saved_before_repair(self):
        conf = self.target / "conf"
        conf.mkdir()
        settings = conf / "settings.properties"
        settings.write_text("Breeding=true\n")
        env = dict(self.env, JAVA_SAVE_SETTINGS=str(settings))
        app = subprocess.Popen([str(self.bin / "java"), "-jar", "./Shimeji-ee.jar"],
                               cwd=self.target, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: app.poll() is None and app.kill())
        self.events()
        self.assertIn(str(app.pid), self.control("--status").stdout)
        self.control("--start")
        self.assertEqual(len(self.events()), 1)
        self.repair("--no-start")
        app.wait(timeout=5)
        self.assertIn("Breeding=false", settings.read_text())
        self.assertIn("ActiveShimeji=Blue/Orange/Yellow/Green", settings.read_text())
        self.assertNotIn("Old", settings.read_text())

    def test_installer_uses_guarded_xdg_launcher_and_custom_config_home(self):
        self.run_script(ROOT / "linux/install.sh", self.target, "--no-hyprland")
        text = (self.config / "autostart/ava-shimeji.desktop").read_text()
        self.assertIn(f'Exec="{self.target}/ava-toggle.sh" --start', text)
        self.assertIn("NotShowIn=Hyprland;", text)
        self.assertNotIn("java -jar", text)
        self.assertFalse((self.home / ".config").exists())
        for name in ("Blue", "Orange", "Yellow", "Green"):
            for xml in (self.target / "img" / name / "conf").glob("*.xml"):
                self.assertNotIn("PullUpShimeji", xml.read_text())
        self.control("--start")
        self.assertEqual(self.events()[0]["cwd"], str(self.target))

    def test_shijima_installed_settings_and_helper(self):
        self.script("shijima-qt", "#!/bin/sh\nexit 0\n")
        self.shijima("--install", "--autostart")
        settings = self.config / "pixelomer/Shijima-Qt.conf"
        self.assertIn("multiplicationEnabled=false", settings.read_text())
        helper = self.home / "data/ava-shimeji/shijima-session.sh"
        self.assertTrue(helper.exists())
        self.assertIn("shijima-session.py", helper.read_text())
        self.assertIn(str(helper), (self.hypr / "ava-shijima-qt.conf").read_text())
        self.assertTrue((helper.parent / "shijima-session.py").exists())
        for name in ("Blue", "Orange", "Yellow", "Green"):
            mascot = self.home / "data/Shijima-Qt/mascots" / (name + ".mascot")
            for xml in mascot.glob("*.xml"):
                self.assertNotIn("PullUpShimeji", xml.read_text())

    def test_missing_config_prints_correct_snippet_without_starting(self):
        (self.hypr / "hyprland.conf").unlink()
        result = self.repair("--syntax", "v3")
        self.assertIn("windowrule = match:class", result.stdout)
        self.assertFalse((self.hypr / "ava-shimeji.conf").exists())
        self.assertFalse((self.home / "java-events").exists())

    def test_flatpak_data_and_settings_match_the_selected_app(self):
        # A stale native import must not receive a Flatpak repair.
        native = self.home / "data/Shijima-Qt/mascots"
        native.mkdir(parents=True)
        (native / "untouched").write_text("keep")
        for app_id in ("com.pixelomer.ShijimaQt", "com.pixelomer.ShijimaQt.Qt"):
            with self.subTest(app_id=app_id):
                self.script("flatpak", "#!/bin/sh\necho " + app_id + "\n")
                self.shijima("--install", "--autostart")
                data = self.home / ".var/app" / app_id
                self.assertTrue((data / "data/Shijima-Qt/mascots/Blue.mascot/actions.xml").exists())
                self.assertIn("multiplicationEnabled=false",
                              (data / "config/pixelomer/Shijima-Qt.conf").read_text())
                helper = self.home / "data/ava-shimeji/shijima-session.sh"
                self.assertIn("flatpak run --env=QT_QPA_PLATFORM=xcb " + app_id, helper.read_text())
        self.assertEqual(list(native.iterdir()), [native / "untouched"])

    def test_reinstall_preserves_shijima_autostart(self):
        self.script("shijima-qt", "#!/bin/sh\nexit 0\n")
        self.shijima("--install", "--autostart")
        rules = self.hypr / "ava-shijima-qt.conf"
        original = rules.read_text()
        self.shijima("--install")
        self.assertEqual(original, rules.read_text())

    def test_stopping_does_not_signal_editor_mentioning_jar(self):
        editor = subprocess.Popen(["python3", "-c", "import time; time.sleep(30)",
                                   "/usr/bin/java -jar " + str(self.target / "Shimeji-ee.jar")],
                                  env=self.env)
        try:
            self.control("--stop")
            self.assertIsNone(editor.poll())
        finally:
            editor.terminate()
            editor.wait(timeout=5)

    def test_failed_java_launch_is_reported(self):
        self.script("java", "#!/bin/sh\nexit 1\n")
        result = self.control("--start", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Java exited during startup", result.stderr)
        self.assertNotIn("Shimejis started", result.stdout)

    def test_existing_xdg_entry_migrates_to_guarded_start(self):
        path = self.config / "autostart/ava-shimeji.desktop"
        path.parent.mkdir()
        original = "[Desktop Entry]\nExec=java -jar old.jar\nX-GNOME-Autostart-enabled=false\nNotShowIn=KDE;\n"
        path.write_text(original)
        for _ in range(2):
            self.repair("--no-start")
        text = path.read_text()
        self.assertIn("NotShowIn=Hyprland;KDE;", text)
        self.assertIn("X-GNOME-Autostart-enabled=true", text)
        self.assertEqual(text.count("Exec="), 1)
        self.assertIn("--start", text)
        self.assertNotIn("java -jar", text)
        self.assertEqual(path.with_name(path.name + ".ava-bak").read_text(), original)

    def test_commented_includes_do_not_count_as_installed_rules(self):
        main = self.hypr / "hyprland.conf"
        main.write_text(f"# source = {self.hypr}/ava-shimeji.conf\n"
                        f"# source = {self.hypr}/ava-shijima-qt.conf\n")
        self.repair("--no-start")
        self.shijima("--install")
        active = [line for line in main.read_text().splitlines() if line.startswith("source =")]
        self.assertEqual(len(active), 2)

    def test_forced_lua_without_lua_config_does_not_start_unruled_windows(self):
        result = self.repair("--syntax", "lua")
        self.assertIn("hl.window_rule", result.stdout)
        self.assertFalse((self.hypr / "ava-shimeji.lua").exists())
        self.assertFalse((self.home / "java-events").exists())

    def mock_shijima_api(self, live):
        self.env["MOCK_LIVE_MASCOTS"] = json.dumps(live)
        self.script("curl", """#!/usr/bin/env python3
import json, os, sys
if any(arg in ("POST", "PUT", "DELETE") for arg in sys.argv):
    sys.exit("diagnostics must not mutate the running app")
if sys.argv[-1].endswith("/loadedMascots"):
    print(json.dumps({"loaded_mascots": [
        {"id": i, "name": name} for i, name in enumerate(("Blue", "Orange", "Yellow", "Green"))
    ]}))
elif sys.argv[-1].endswith("/mascots"):
    print(os.environ["MOCK_LIVE_MASCOTS"])
else:
    sys.exit(1)
""")

    def test_shijima_check_counts_live_copies_and_explains_shared_box_without_writing(self):
        self.mock_shijima_api({"mascots": [
            {"id": i, "name": name} for i, name in enumerate(
                ("Blue", "Blue", "Blue", "Orange", "Orange", "Green"))
        ]})
        before = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        result = self.shijima("--check")
        self.assertIn("live mascot count         : 6", result.stdout)
        self.assertIn("Blue: 3 (extra copies)", result.stdout)
        self.assertIn("Orange: 2 (extra copies)", result.stdout)
        self.assertIn("ONE shared box", result.stdout)
        self.assertIn("uncheck Enable multiplication, then uncheck Windowed mode", result.stdout)
        self.assertIn("Dismiss all", result.stdout)
        self.assertIn("API does not report or change this mode", result.stdout)
        self.assertNotIn("curl -X POST", result.stdout)
        self.assertNotIn("Spawn one by hand", result.stdout)
        after = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_shijima_check_reports_unknown_for_invalid_live_response(self):
        self.mock_shijima_api({})
        result = self.shijima("--check")
        self.assertIn("live mascot count         : unknown", result.stdout)
        self.assertNotIn("live mascot count         : 0", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_shijima_check_accepts_genuinely_empty_screen(self):
        self.mock_shijima_api({"mascots": []})
        result = self.shijima("--check")
        self.assertIn("live mascot count         : 0", result.stdout)
        self.assertNotIn("extra copies", result.stdout)


if __name__ == "__main__":
    unittest.main()
