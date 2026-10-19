import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("ava_runner", "runner/ava_runner.py")
validator = load("validate_pack", "tools/validate.py")


class RunnerTests(unittest.TestCase):
    def test_wayland_uses_xcb_instead_of_unpositionable_wayland_toplevels(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0",
                                    "QT_QPA_PLATFORM": "wayland"}, clear=True):
            runner.prepare_desktop()
            self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb")

    def test_wayland_without_xwayland_fails_with_actionable_error(self):
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "XWayland.*DISPLAY"):
                runner.prepare_desktop()

    def test_non_wayland_platform_override_is_left_alone(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}, clear=True):
            runner.prepare_desktop()
            self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")

    def test_validator_rejects_even_zero_frequency_cloning(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(validator, "ROOT", folder):
            conf = Path(folder) / "AVA Shimejis/Blue/conf"
            conf.mkdir(parents=True)
            (conf / "actions.xml").write_text('''<Mascot><ActionList>
<Action Name="PullUpShimeji" Type="Embedded" Class="com.group_finity.mascot.action.Breed"/>
</ActionList></Mascot>''')
            (conf / "behaviors.xml").write_text('''<Mascot><BehaviorList>
<Behavior Name="PullUpShimeji" Frequency="0"/>
</BehaviorList></Mascot>''')
            failures = []
            validator.check_xml("Blue", failures)
            self.assertTrue(any("zero frequency" in error for error in failures))
            self.assertTrue(any("cloning action" in error for error in failures))


if __name__ == "__main__":
    unittest.main()
