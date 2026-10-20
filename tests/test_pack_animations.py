import xml.etree.ElementTree as ET
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHARS = ("Blue", "Orange", "Yellow", "Green")
NS = {"m": "http://www.group-finity.com/Mascot"}


class MascotAnimationRegressionTests(unittest.TestCase):
    def read_pack(self, char):
        base = ROOT / "AVA Shimejis" / char
        return base, ET.parse(base / "conf/actions.xml").getroot(), \
            ET.parse(base / "conf/behaviors.xml").getroot()

    def action(self, root, name):
        return root.find(f'.//m:Action[@Name="{name}"]', NS)

    def test_climb_poses_are_smooth_and_reverse_when_descending(self):
        for char in CHARS:
            with self.subTest(char=char):
                base, actions, _ = self.read_pack(char)
                wall = self.action(actions, "ClimbWall")
                animations = wall.findall("m:Animation", NS)
                self.assertEqual(len(animations), 2)
                up, down = [[p for p in animation.findall("m:Pose", NS)]
                            for animation in animations]
                self.assertEqual(len(up), 5)
                self.assertEqual(len(down), 5)
                expected = [f"/wall_climb{i:02}.png" for i in range(1, 6)]
                self.assertEqual([p.get("Image") for p in up], expected)
                self.assertEqual([p.get("Image") for p in down], expected[::-1])
                self.assertEqual({p.get("Velocity") for p in up}, {"0,-3"})
                self.assertEqual({p.get("Velocity") for p in down}, {"0,3"})
                self.assertEqual({p.get("Duration") for p in up + down}, {"4"})

                ceiling = self.action(actions, "ClimbCeiling")
                poses = ceiling.findall(".//m:Pose", NS)
                self.assertEqual(len(poses), 8)
                self.assertEqual({p.get("Image") for p in poses},
                                 {f"/swing{i:02}.png" for i in range(1, 9)})
                self.assertEqual({p.get("Velocity") for p in poses}, {"-4,0"})
                self.assertEqual([p.get("Duration") for p in poses],
                                 ["3", "3", "4", "3", "3", "4", "3", "3"])

                for pose in wall.findall(".//m:Pose", NS) + poses:
                    self.assertTrue((base / pose.get("Image").lstrip("/")).is_file())

    def test_climb_sequences_use_supported_random_function_calls(self):
        for char in CHARS:
            with self.subTest(char=char):
                _, actions, _ = self.read_pack(char)
                along_wall = ET.tostring(self.action(actions, "ClimbAlongWall"),
                                         encoding="unicode")
                self.assertIn("Math.random()", along_wall)
                self.assertNotIn("Math.random*", along_wall)
                self.assertIsNotNone(self.action(actions, "ClimbHalfwayAlongWall"))
                self.assertIsNotNone(self.action(actions, "ClimbAlongCeiling"))

    def test_dance_only_starts_on_the_real_floor_and_has_no_chained_exit(self):
        dance_weights = set()
        dance_durations = {}
        for char in CHARS:
            with self.subTest(char=char):
                base, actions, behaviors = self.read_pack(char)
                action = self.action(actions, "Dance")
                self.assertEqual(action.get("Type"), "Animate")
                self.assertEqual(action.get("BorderType"), "Floor")
                self.assertEqual(action.get("Condition"),
                                 "#{mascot.environment.floor.isOn(mascot.anchor)}")
                poses = action.findall(".//m:Pose", NS)
                self.assertTrue(poses)
                for pose in poses:
                    self.assertEqual(pose.get("Velocity"), "0,0")
                    self.assertTrue((base / pose.get("Image").lstrip("/")).is_file())
                dance_durations[char] = tuple(p.get("Duration") for p in poses)

                entries = behaviors.findall('.//m:Behavior[@Name="Dance"]', NS)
                self.assertEqual(len(entries), 1)
                behavior = entries[0]
                self.assertEqual(behavior.get("Condition"),
                                 "#{mascot.environment.floor.isOn(mascot.anchor)}")
                self.assertEqual(len(behavior.findall("m:NextBehavior", NS)), 0)
                dance_weights.add(behavior.get("Frequency"))
        self.assertEqual(len(dance_weights), 4)
        self.assertEqual(len(set(dance_durations.values())), 4)

    def test_character_behavior_pools_have_distinct_order_and_weights(self):
        orders = []
        dance_weights = []
        for char in CHARS:
            _, _, behaviors = self.read_pack(char)
            generated = behaviors.find("m:BehaviorList", NS)
            names = [e.get("Name") for e in generated
                     if e.tag.endswith("Behavior") and e.get("Name")]
            orders.append(tuple(names))
            dance_weights.append(next(e.get("Frequency") for e in generated
                                      if e.tag.endswith("Behavior") and
                                      e.get("Name") == "Dance"))
        self.assertEqual(len(set(orders)), 4)
        self.assertEqual(len(set(dance_weights)), 4)


if __name__ == "__main__":
    unittest.main()
