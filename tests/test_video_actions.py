"""Source provenance and playback-contract tests for video-derived additions."""
import hashlib
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NS = {'m': 'http://www.group-finity.com/Mascot'}


class VideoActionTests(unittest.TestCase):
    def test_source_and_all_four_existing_figures(self):
        data = json.loads((ROOT/'tools/video_actions.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/data['source']).read_bytes()).hexdigest(), data['sha256'])
        self.assertEqual({a['character'] for a in data['actions']}, {'Orange','Blue','Green','Yellow'})
        self.assertEqual(len(data['actions']), 8)

    def test_single_pass_then_roaming_and_valid_art(self):
        for a in json.loads((ROOT/'tools/video_actions.json').read_text())['actions']:
            with self.subTest(character=a['character'], action=a['name']):
                base = ROOT/'AVA Shimejis'/a['character']
                actions = ET.parse(base/'conf/actions.xml')
                behavior = ET.parse(base/'conf/behaviors.xml')
                node = actions.find(f'.//m:Action[@Name="{a["name"]}"]', NS)
                self.assertIsNotNone(node)
                self.assertEqual(node.get('Loop'), 'false')
                poses = node.findall('.//m:Pose', NS)
                self.assertEqual([p.get('Image').lstrip('/') for p in poses], a['frames'])
                self.assertEqual(len(set(a['frames'])), len(a['frames']))
                self.assertEqual({p.get('Duration') for p in poses}, {'1'})
                self.assertLessEqual(abs(len(poses)*.04-(a['source_interval'][1]-a['source_interval'][0])), .04+1e-6)
                b = behavior.find(f'.//m:Behavior[@Name="{a["name"]}"]', NS)
                nxt = b.find('m:NextBehaviorList', NS)
                self.assertEqual(nxt.get('Add'), 'false')
                self.assertEqual({r.get('Name') for r in nxt}, {'WalkAlongWorkAreaFloor','RunAlongWorkAreaFloor'})
                for filename in a['frames']:
                    with Image.open(base/filename) as im:
                        self.assertEqual(im.size,(160,160))
                        self.assertEqual(im.mode,'RGBA')
                        box = im.getbbox()
                        self.assertIsNotNone(box)
                        self.assertGreaterEqual(min(box[0],box[1],160-box[2],160-box[3]),8)


if __name__ == '__main__':
    unittest.main()
