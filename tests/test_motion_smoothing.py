"""Smoothing preserves approved source poses and playback contracts."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class SmoothingContractTests(unittest.TestCase):
    def test_climbing_keeps_cycle_duration_and_displacement(self):
        source=json.loads((ROOT/'third_party/alan-stickfigures/source.json').read_text())
        output=json.loads((ROOT/'tools/classic_climbing.json').read_text())
        for char,entry in output.items():
            scale=entry['scale']
            for action in ('ClimbWall','ClimbCeiling'):
                original=source['characters'][char][action]
                poses=entry['actions'][action]
                self.assertEqual(sum(int(p['Duration']) for p in original),len(poses))
                self.assertEqual({p[3] for p in poses},{1})
                for axis in (0,1):
                    def scaled(v):
                        return (1 if v>0 else -1)*max(1,round(abs(v)*scale)) if v else 0
                    expected=sum(scaled(int(p['Velocity'].split(',')[axis]))*int(p['Duration']) for p in original)
                    actual=sum(int(p[2].split(',')[axis])*p[3] for p in poses)
                    self.assertEqual(actual,expected)
                self.assertEqual(len(entry['keyframes'][action]),len(original))

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'baseline masks require NumPy')
    def test_new_actions_keep_endpoints_and_coverage(self):
        import numpy as np
        source=ROOT/'third_party/video-motion-baseline'
        metadata=json.loads((source/'source.json').read_text())
        with np.load(source/'frames.npz',allow_pickle=False) as archive:
            for key,a in metadata['actions'].items():
                for i,name in enumerate(a['frames']):
                    actual=np.asarray(Image.open(ROOT/'AVA Shimejis'/a['character']/name).convert('RGBA'))
                    baseline=archive[key][i]
                    if i in (0,len(a['frames'])-1):
                        self.assertTrue(np.array_equal(actual,baseline))
                    ratio=actual[:,:,3].sum()/baseline[:,:,3].sum()
                    self.assertGreaterEqual(ratio,.895)
                    self.assertLessEqual(ratio,1.105)

    @unittest.skipUnless(importlib.util.find_spec('cv2'), 'offline smoothing requires OpenCV')
    def test_tween_retains_exact_endpoints(self):
        from motion_smoothing import tween
        path=ROOT/'third_party/alan-stickfigures/Blue'
        a=Image.open(path/'swing01.png').convert('RGBA')
        b=Image.open(path/'swing02.png').convert('RGBA')
        self.assertEqual(tween(a,b,0).tobytes(),a.tobytes())
        self.assertEqual(tween(a,b,1).tobytes(),b.tobytes())


if __name__=='__main__':unittest.main()
