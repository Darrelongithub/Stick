"""Every pose in the pack must sit on one shared skeleton.

The complaint this guards against: the same character looked bigger in one
animation, then normal again in the next, with a 40px forearm in one move and a
5px neck in another.  ``stickgen.normalize_pose`` rebuilds every authored pose
on the reference bone lengths, so these tests check the *drawn* skeleton rather
than the numbers each rig happens to author.
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stickgen  # noqa: E402


# Continuous rigs: every frame is generated from the previous one, so a joint
# must never jump.  Pose-to-pose moves (a punch, a wave, a stumble) are authored
# as discrete drawings and are deliberately not listed here.
CONTINUOUS_RIGS = {
    "idle": 4.0,
    "crawl": 2.5,
    "wall_climb": 4.0,
    "wall_hold": 2.5,
    "hang": 2.5,
    "swing": 5.0,
    "cartwheel": 12.0,   # whole-body rotation: the head honestly travels far
    "jumprope": 6.0,
    "fall": 4.0,         # freefall: an orientated body with a slow flail
}


class FigureProportionTests(unittest.TestCase):
    def test_every_bone_is_the_reference_length_in_every_frame(self):
        for anim, frames in stickgen.ANIMS.items():
            for index, frame in enumerate(frames):
                pose = stickgen.normalize_pose(frame)
                for (parent, joint), key in stickgen._BONE_LENGTH.items():
                    with self.subTest(anim=anim, frame=index + 1,
                                      bone=f"{parent}->{joint}"):
                        self.assertAlmostEqual(
                            math.dist(pose[parent], pose[joint]),
                            stickgen.PROPORTIONS[key], places=2)

    def test_left_and_right_limbs_are_the_same_length(self):
        """A pose cannot end up with one arm longer than the other."""
        pairs = (("SH", "EL", "SH", "ER"), ("EL", "HL", "ER", "HR"),
                 ("HIP", "KL", "HIP", "KR"), ("KL", "FL", "KR", "FR"))
        for anim, frames in stickgen.ANIMS.items():
            for index, frame in enumerate(frames):
                pose = stickgen.normalize_pose(frame)
                for near_parent, near, far_parent, far in pairs:
                    with self.subTest(anim=anim, frame=index + 1,
                                      bone=f"{near}/{far}"):
                        self.assertAlmostEqual(
                            math.dist(pose[near_parent], pose[near]),
                            math.dist(pose[far_parent], pose[far]), places=2)

    def test_generation_report_lists_no_proportion_or_continuity_errors(self):
        self.assertEqual(stickgen.proportion_errors(), [])
        self.assertEqual(stickgen.continuity_errors(), [])

    def test_continuous_rigs_never_snap_a_joint(self):
        for anim, limit in CONTINUOUS_RIGS.items():
            frames = stickgen.ANIMS[anim]
            for joint in stickgen.STAND:
                with self.subTest(anim=anim, joint=joint):
                    worst = max(
                        math.dist(stickgen._full_joints(frames[i])[joint],
                                  stickgen._full_joints(
                                      frames[(i + 1) % len(frames)])[joint])
                        for i in range(len(frames)))
                    self.assertLessEqual(worst, limit)

    def test_contact_rigs_keep_every_target_within_reach(self):
        """A fixed-length limb cannot be teleported onto a distant contact.

        If a rig ever asks for one, ``crawl_limb`` raises instead of clamping
        the reach and bending the limb straight; this simply proves every
        shipped rig stays inside that budget while it is built.
        """
        for name, builder, count in (
                ("crawl", stickgen.GROUND_CRAWL_FRAME, 48),
                ("wall_climb", stickgen.WALL_CLIMB_FRAME, 48),
                ("wall_hold", stickgen.WALL_HOLD_FRAME, 16),
                ("hang", stickgen.CEILING_HOLD_FRAME, 16),
                ("swing", stickgen.CEILING_SWING_FRAME, 48)):
            with self.subTest(rig=name):
                stickgen._chain(builder, count)

    def test_falling_stays_upright_instead_of_tumbling(self):
        """Falling is a fall, not a somersault: the rig used to rotate a full
        360 degrees every cycle, which is what made it read as a cartwheel."""
        frames = stickgen.ANIMS["fall"]
        self.assertEqual(len(frames), 48)
        for index, frame in enumerate(frames):
            pose = stickgen.normalize_pose(frame)
            head_up = pose["HIP"][1] - pose["H"][1]
            with self.subTest(frame=index + 1):
                self.assertGreater(head_up, 30.0)   # head always above the hips
                self.assertNotIn("rot", frame)      # no whole-body spin

    def test_the_neck_is_one_short_length(self):
        """The 'why does Yellow suddenly have a long neck' bug."""
        neck = stickgen.PROPORTIONS["neck"]
        self.assertLess(neck, stickgen.PROPORTIONS["neck-shoulder"] * 1.5)
        for anim, frames in stickgen.ANIMS.items():
            for index, frame in enumerate(frames):
                pose = stickgen.normalize_pose(frame)
                with self.subTest(anim=anim, frame=index + 1):
                    self.assertAlmostEqual(
                        math.dist(pose["H"], pose["N"]), neck, places=2)


if __name__ == "__main__":
    unittest.main()
