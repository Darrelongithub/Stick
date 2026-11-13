"""ShimeLinux wall holds should branch, not always release or descend."""
import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import patch_xml


class WallRouteTests(unittest.TestCase):
    def test_each_character_has_three_weighted_successors(self):
        preferences = set()
        for char in patch_xml.WALL_ROUTE_WEIGHTS:
            root = ET.parse(ROOT/'AVA Shimejis'/char/'conf/behaviors.xml').getroot()
            hold = next(e for e in root.iter() if e.tag.split('}')[-1] == 'Behavior' and e.get('Name') == 'HoldOntoWall')
            successors = list(hold)[0]
            self.assertEqual(successors.tag.split('}')[-1], 'NextBehaviorList')
            self.assertEqual(successors.get('Add'), 'false')
            refs = list(successors)
            self.assertEqual([r.get('Name') for r in refs], ['ClimbAlongWall', 'ClimbHalfwayAlongWall', 'FallFromWall'])
            weights = tuple(int(r.get('Frequency')) for r in refs)
            self.assertTrue(all(w > 0 for w in weights))
            preferences.add(weights)
            for r in refs[:2]:
                self.assertIn('rightBorder.isOn', r.get('Condition'))
                self.assertIn('workArea.top+64', r.get('Condition'))
        self.assertEqual(len(preferences), 4)

    def test_partial_target_ascends_from_current_height(self):
        for char in patch_xml.WALL_ROUTE_WEIGHTS:
            root = ET.parse(ROOT/'AVA Shimejis'/char/'conf/actions.xml').getroot()
            action = next(e for e in root.iter() if e.get('Name') == 'ClimbHalfwayAlongWall' and e.tag.split('}')[-1] == 'Action')
            self.assertEqual(list(action)[0].get('TargetY'), '${mascot.anchor.y-(mascot.anchor.y-mascot.environment.workArea.top-64)*(0.25+Math.random()*0.5)}')
        for y in (100, 500, 1000):
            for r in (0, .5, .999):
                target = y-(y-64)*(.25+r*.5)
                self.assertLess(target, y)
                self.assertGreater(target, 64)

    def test_successor_rewrite_is_idempotent(self):
        for char in patch_xml.WALL_ROUTE_WEIGHTS:
            raw = (ROOT/'AVA Shimejis'/char/'conf/behaviors.xml').read_text()
            self.assertEqual(raw, patch_xml.wall_route_successors(raw, char, '\n'))


if __name__ == '__main__':
    unittest.main()
