import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_mascots", ROOT / "linux/configure-mascots.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class SettingsTests(unittest.TestCase):
    def test_java_duplicate_keys_whitespace_crlf_and_missing_final_newline(self):
        text = ("# settings\r\nSound=true\r\nBreeding=true\r\n Breeding : true\r\n"
                "Breeding true\r\nActiveShimeji=Old\r\nActiveShimeji = Other")
        values = {"Breeding": "false", "ActiveShimeji": "Blue/Orange/Yellow/Green"}
        fixed = config.properties(text, values)
        self.assertEqual(fixed.count("Breeding="), 1)
        self.assertEqual(fixed.count("ActiveShimeji="), 1)
        self.assertIn("Sound=true\r\n", fixed)
        self.assertNotIn("\n", fixed.replace("\r\n", ""))
        self.assertEqual(config.properties(fixed, values), fixed)

    def test_installed_old_breeding_xml_removed_and_first_backup_kept(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            target = Path(folder)
            conf = target / "img/Blue/conf"
            conf.mkdir(parents=True)
            action = conf / "actions.xml"
            behavior = conf / "behaviors.xml"
            action.write_text('''<Mascot><ActionList>
<Action Name="Walk" Type="Move"/>
<Action Name="PullUpShimeji" Type="Sequence"><ActionReference Name="PullUpShimeji1"/></Action>
<Action Name="PullUpShimeji1" Type="Embedded" Class="com.group_finity.mascot.action.Breed"/>
</ActionList></Mascot>''')
            behavior.write_text('''<Mascot><BehaviorList>
<Behavior Name="PullUpShimeji" Frequency="0"/>
<Behavior Name="Walk" Frequency="10"><BehaviorReference Name="PullUpShimeji"/></Behavior>
</BehaviorList></Mascot>''')
            old = action.read_bytes()
            other = target / "img/Other/conf/actions.xml"
            other.parent.mkdir(parents=True)
            other.write_text("leave somebody else's mascot alone")
            config.configure_shimeji(target)
            first = action.read_bytes()
            config.configure_shimeji(target)
            self.assertEqual(first, action.read_bytes())
            self.assertEqual(action.with_name("actions.xml.ava-bak").read_bytes(), old)
            self.assertNotIn("PullUpShimeji", action.read_text() + behavior.read_text())
            self.assertIn('Name="Walk"', action.read_text())
            self.assertEqual(other.read_text(), "leave somebody else's mascot alone")
            self.assertIn("Breeding=false", (target / "conf/settings.properties").read_text())

    def test_qsettings_preserves_other_sections_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / "settings.conf"
            original = (b"[General]\r\nuserScale=1.25\r\nmultiplicationEnabled=true\r\n"
                        b"multiplicationEnabled=true\r\n[Other]\r\nvalue=@ByteArray(foo)\r\n")
            path.write_bytes(original)
            config.configure_shijima(path)
            first = path.read_bytes()
            config.configure_shijima(path)
            self.assertEqual(first, path.read_bytes())
            self.assertEqual(path.with_name("settings.conf.ava-bak").read_bytes(), original)
            self.assertEqual(first.count(b"multiplicationEnabled=false"), 1)
            # Upstream does not read a windowedMode key. Don't pretend a disk
            # setting can turn off the running app's shared sandbox window.
            self.assertNotIn(b"windowedMode=", first)
            self.assertIn(b"userScale=1.25\r\n", first)
            self.assertIn(b"[Other]\r\nvalue=@ByteArray(foo)\r\n", first)

    def test_qsettings_general_missing_or_empty(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / "settings.conf"
            for text in ("", "[Other]\nvalue=keep\n", "[General]\n[Other]\nvalue=keep\n"):
                path.write_text(text)
                config.configure_shijima(path)
                fixed = path.read_text()
                self.assertEqual(fixed.count("[General]"), 1)
                self.assertIn("[General]\nmultiplicationEnabled=false\n", fixed)
                self.assertIn(text.split("[Other]")[-1], fixed)


if __name__ == "__main__":
    unittest.main()
