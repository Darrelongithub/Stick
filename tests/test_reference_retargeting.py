"""Guard actual reference-driven changes, not just internal bone consistency."""
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import stickgen as rig


class ReferenceRetargetingTests(unittest.TestCase):
    def test_reference_body_ratios(self):
        p = rig.PROPORTIONS
        diameter = 2*rig.HEAD_R
        self.assertAlmostEqual((p['neck']+p['neck-shoulder'])/diameter, .6125)
        self.assertTrue(2.10 < (p['thigh']+p['shin'])/diameter < 2.22)
        self.assertTrue(1.10 < (p['upper arm']+p['forearm'])/diameter < 1.18)

    def test_orange_is_hollow_and_larger_than_blue(self):
        # Inspect head region only; comparing the whole silhouette's width
        # would mistake a wide stance or an outstretched hand for head size.
        blue = np.array(rig.render_frame(rig.BODY['Blue'], 'idle', 0))
        orange = np.array(rig.render_frame(rig.BODY['Orange'], 'idle', 0))
        def head_width(a):
            mask = a[:70, :, 3] > 128
            spans = []
            for row in mask:
                xx = np.flatnonzero(row)
                if len(xx):
                    spans.append(xx[-1]-xx[0]+1)
            return max(spans)
        self.assertGreater(head_width(orange), head_width(blue)*1.4)
        # The empty center is an enclosed transparent region, not background
        # paint or a solid disk with a dark fill.
        from scipy.ndimage import binary_fill_holes
        mask = orange[:, :, 3] > 128
        self.assertGreater(int((binary_fill_holes(mask) & ~mask).sum()), 250)

    def test_floor_idle_does_not_sink_with_longer_legs(self):
        for char in rig.BODY:
            for i in range(len(rig.ANIMS['idle'])):
                image = rig.render_frame(rig.BODY[char], 'idle', i)
                self.assertLessEqual(image.getbbox()[3], 144)


if __name__ == '__main__':
    unittest.main()
