"""Guard native pickup and roaming XML while reference art is revised.

These are configuration tests, not proof of live mouse/window interaction.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class InteractionContract(unittest.TestCase):
    def test_pickup_and_target_driven_roaming_remain_available(self):
        for char in ('Blue', 'Orange', 'Yellow', 'Green'):
            with self.subTest(character=char):
                conf = ROOT / 'AVA Shimejis' / char / 'conf'
                tree = ET.parse(conf / 'actions.xml')
                actions = {e.get('Name'): e for e in tree.iter()
                           if e.tag.rsplit('}', 1)[-1] == 'Action'}
                dragged = actions['Dragged']
                refs = [e.get('Name') for e in dragged.iter()
                        if e.tag.rsplit('}', 1)[-1] == 'ActionReference']
                self.assertIn('Pinched', refs)
                self.assertEqual(actions['Pinched'].get('Class'),
                                 'com.group_finity.mascot.action.Dragged')
                for name in ('Walk', 'Run'):
                    self.assertEqual(actions[name].get('Type'), 'Move')
                for name in ('WalkAlongWorkAreaFloor', 'RunAlongWorkAreaFloor'):
                    self.assertTrue(any(e.get('TargetX') for e in actions[name].iter()))
                behaviors = ET.parse(conf / 'behaviors.xml')
                names = {e.get('Name') for e in behaviors.iter()
                         if e.tag.rsplit('}', 1)[-1] == 'Behavior'}
                self.assertTrue({'Dragged', 'Thrown', 'Fall'} <= names)


if __name__ == '__main__':
    unittest.main()
