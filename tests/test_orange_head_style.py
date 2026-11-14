"""Orange must retain its transparent head interior across artwork families."""
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from normalize_orange_heads import REGIONS, hollow, normalize


class OrangeHeadTests(unittest.TestCase):
    def test_all_reviewed_centers_are_transparent_and_normalization_is_idempotent(self):
        self.assertEqual(len(REGIONS), len({r[0] for r in REGIONS}))
        for name, x, y, radius in REGIONS:
            with self.subTest(frame=name):
                im = Image.open(ROOT/'AVA Shimejis/Orange'/name).convert('RGBA')
                self.assertEqual(im.getpixel((x, y))[3], 0)
                self.assertEqual(normalize(im, name).tobytes(), im.tobytes())

    def test_cut_changes_only_interior_alpha_not_outer_art_or_rgb(self):
        im = Image.new('RGBA', (64, 64), (242, 111, 36, 255))
        a = np.array(im)
        b = np.array(hollow(im, 32, 32, 12))
        np.testing.assert_array_equal(a[:, :, :3], b[:, :, :3])
        yy, xx = np.indices((64, 64))
        outside = np.hypot(xx-32, yy-32) >= 9
        np.testing.assert_array_equal(a[outside], b[outside])
        self.assertEqual(a.shape, b.shape)

    def test_unlisted_source_art_is_untouched(self):
        for name in ('wall_climb_smooth01.png', 'hang01.png', 'videoref_videoleanstep_001.png'):
            im = Image.open(ROOT/'AVA Shimejis/Orange'/name).convert('RGBA')
            self.assertEqual(normalize(im, name).tobytes(), im.tobytes())


if __name__ == '__main__':
    unittest.main()
