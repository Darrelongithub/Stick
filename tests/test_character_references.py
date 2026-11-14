"""Each character must use its own selected master pose, not shared medians."""
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import stickgen as rig
from character_reference import PROFILES, REFERENCE


class CharacterReferenceTests(unittest.TestCase):
    def test_profiles_come_from_each_selected_frame(self):
        self.assertEqual(set(PROFILES), set(rig.BODY))
        for character, profile in PROFILES.items():
            points = REFERENCE['characters'][character]
            radius = 18 if character == 'Orange' else 12
            factor = radius/points['radius']
            self.assertAlmostEqual(profile['torso'], math.dist(points['shoulder'], points['hip'])*factor)
            self.assertAlmostEqual(profile['thigh'], math.dist(points['hip'], points['knee'])*factor)
            self.assertAlmostEqual(profile['shin'], math.dist(points['knee'], points['foot'])*factor)
        self.assertEqual(len({tuple(p.values()) for p in PROFILES.values()}), 4)

    def test_render_selects_correct_character_not_default_rig(self):
        for character, rgb in rig.BODY.items():
            with patch.object(rig, 'normalize_pose', wraps=rig.normalize_pose) as normalize:
                rig.render_frame(rgb, 'idle', 0)
                self.assertIs(normalize.call_args.kwargs['proportions'], PROFILES[character])

    def test_every_generated_pose_against_its_own_master(self):
        for character, target in PROFILES.items():
            for action in rig.SPEC.generated_actions_for(character):
                if rig.SPEC.ACTIONS[action].get('source_authored'):
                    continue
                for i, name in enumerate(rig.SPEC.frame_names(action)):
                    authored = rig.ANIMS[rig._anim_key_for(action, i)][rig._anim_index(action, i)]
                    pose = rig.normalize_pose(authored, proportions=target)
                    for (parent, joint), key in rig._BONE_LENGTH.items():
                        with self.subTest(character=character, frame=name, bone=key):
                            self.assertAlmostEqual(math.dist(pose[parent],pose[joint]),target[key],places=6)


if __name__ == '__main__':
    unittest.main()
