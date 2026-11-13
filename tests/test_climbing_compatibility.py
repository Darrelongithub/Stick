"""Climbing regressions: native config parser and grip geometry."""
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import stickgen
import validate


class ClimbingCompatibilityTests(unittest.TestCase):
    def test_validator_rejects_decimal_velocity_before_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / 'AVA Shimejis/Blue/conf'
            shutil.copytree(ROOT / 'AVA Shimejis/Blue/conf', conf)
            path = conf / 'actions.xml'
            raw = path.read_text()
            self.assertIn('Velocity="-4,0"', raw)
            path.write_text(raw.replace('Velocity="-4,0"', 'Velocity="-0.42,0"', 1))
            failures = []
            with patch.object(validate, 'ROOT', tmp):
                validate.check_xml('Blue', failures)
            self.assertTrue(any('non-integer Velocity' in f for f in failures), failures)

    def test_source_images_are_not_procedural_substitutes(self):
        import json
        from PIL import Image
        data = json.loads((ROOT/'tools/classic_climbing.json').read_text())
        for char, entry in data.items():
            scale = entry['scale']
            for name, keyframes in entry['keyframes'].items():
                for key in keyframes:
                    filename = key['file']
                    src = Image.open(ROOT/'third_party/alan-stickfigures'/char/key['source']).convert('RGBA')
                    size = (round(src.width*scale), round(src.height*scale))
                    if size != src.size:
                        src = src.resize(size, Image.Resampling.LANCZOS)
                    expected = Image.new('RGBA',(160,160))
                    expected.alpha_composite(src,(16,16))
                    actual = Image.open(ROOT/'AVA Shimejis'/char/filename).convert('RGBA')
                    self.assertEqual(actual.tobytes(), expected.tobytes())


if __name__ == '__main__':
    unittest.main()
