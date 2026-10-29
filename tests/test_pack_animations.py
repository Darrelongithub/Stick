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

    def test_climb_poses_are_smooth_phased_and_reverse_when_descending(self):
        phase = {"Blue": 0, "Orange": 12, "Yellow": 24, "Green": 36}
        for char in CHARS:
            with self.subTest(char=char):
                base, actions, _ = self.read_pack(char)
                wall = self.action(actions, "ClimbWall")
                animations = wall.findall("m:Animation", NS)
                self.assertEqual(len(animations), 2)
                up, down = [[p for p in animation.findall("m:Pose", NS)]
                            for animation in animations]
                self.assertEqual(len(up), 48)
                self.assertEqual(len(down), 48)
                natural = [f"/wall_climb{i:02}.png" for i in range(1, 49)]
                offset = phase[char]
                expected = natural[offset:] + natural[:offset]
                self.assertEqual([p.get("Image") for p in up], expected)
                self.assertEqual([p.get("Image") for p in down], expected[::-1])
                self.assertEqual({p.get("Velocity") for p in up}, {"0,-1"})
                self.assertEqual({p.get("Velocity") for p in down}, {"0,1"})
                self.assertEqual({p.get("Duration") for p in up + down}, {"1"})

                ceiling = self.action(actions, "ClimbCeiling")
                poses = ceiling.findall(".//m:Pose", NS)
                self.assertEqual(len(poses), 48)
                natural = [f"/swing{i:02}.png" for i in range(1, 49)]
                expected = natural[offset:] + natural[:offset]
                self.assertEqual([p.get("Image") for p in poses], expected)
                self.assertEqual({p.get("Velocity") for p in poses}, {"-1,0"})
                self.assertEqual({p.get("Duration") for p in poses}, {"1"})

                # Waiting for the next edge route must remain animated too.
                for hold_name, prefix in (("GrabCeiling", "hang"),
                                          ("GrabWall", "wall_hold")):
                    hold = self.action(actions, hold_name).findall(".//m:Pose", NS)
                    self.assertEqual(len(hold), 16)
                    self.assertEqual(len({p.get("Image") for p in hold}), 16)
                    self.assertEqual({p.get("Duration") for p in hold}, {"2"})
                    self.assertTrue(all(p.get("Image", "").startswith(f"/{prefix}")
                                        for p in hold))
                    self.assertTrue(all((base / p.get("Image").lstrip("/")).is_file()
                                        for p in hold))

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

    def test_falling_and_ground_crawl_are_full_cycles_not_held_statues(self):
        first_images = {"Falling": set(), "Crawl": set()}
        for char in CHARS:
            with self.subTest(char=char):
                base, actions, _ = self.read_pack(char)
                for name, prefix, velocity, duration in (
                        ("Falling", "fall", "0,0", "1"),
                        ("Crawl", "crawl", "-1,0", "1")):
                    action = self.action(actions, name)
                    poses = action.findall(".//m:Pose", NS)
                    self.assertEqual(len(poses), 48)
                    self.assertEqual({p.get("Image") for p in poses},
                                     {f"/{prefix}{i:02}.png" for i in range(1, 49)})
                    self.assertEqual({p.get("Duration") for p in poses}, {duration})
                    self.assertEqual({p.get("Velocity") for p in poses}, {velocity})
                    first_images[name].add(poses[0].get("Image"))
                    for pose in poses:
                        self.assertTrue((base / pose.get("Image").lstrip("/")).is_file())
        # Stable quarter-cycle offsets break lockstep even under identical seeds.
        self.assertEqual(len(first_images["Falling"]), 4)
        self.assertEqual(len(first_images["Crawl"]), 4)

    def test_stand_is_an_animated_idle_and_long_rest_references_are_capped(self):
        for char in CHARS:
            with self.subTest(char=char):
                _, actions, _ = self.read_pack(char)
                stand = self.action(actions, "Stand")
                poses = stand.findall(".//m:Pose", NS)
                self.assertEqual(len(poses), 8)
                self.assertEqual(len({p.get("Image") for p in poses}), 8)
                self.assertTrue(all(p.get("Image", "").startswith("/idle") for p in poses))
                self.assertLessEqual(max(int(p.get("Duration")) for p in poses), 4)
                affordance = self.action(actions, "StandAffordance")
                affordance_poses = affordance.findall(".//m:Pose", NS)
                self.assertEqual(len(affordance_poses), 8)
                self.assertTrue(all(p.get("Image", "").startswith("/idle")
                                    for p in affordance_poses))
                xml = ET.tostring(actions, encoding="unicode")
                self.assertNotIn("500+Math.random()*1000", xml)
                self.assertNotIn(r"\D\.png", xml)

    def test_each_character_has_a_second_exclusive_move(self):
        exclusive = {"Blue": ("ReadBook", 8), "Orange": ("Cartwheel", 48),
                     "Yellow": ("Inspect", 8), "Green": ("JumpRope", 24)}
        for char, (name, frame_count) in exclusive.items():
            with self.subTest(char=char):
                base, actions, behaviors = self.read_pack(char)
                action = self.action(actions, name)
                self.assertIsNotNone(action)
                poses = action.findall(".//m:Pose", NS)
                self.assertEqual(len(poses), frame_count)
                if name in ("Cartwheel", "JumpRope"):
                    self.assertEqual({p.get("Duration") for p in poses}, {"1"})
                self.assertEqual(len(behaviors.findall(f'.//m:Behavior[@Name="{name}"]', NS)), 1)
                self.assertTrue(all((base / p.get("Image").lstrip("/")).is_file()
                                    for p in poses))
                for other in set(CHARS) - {char}:
                    _, other_actions, _ = self.read_pack(other)
                    self.assertIsNone(self.action(other_actions, name))

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
                # Dance still only starts on the real floor; the crew-slot and
                # no-repeat rules are ANDed on top of that gate.
                self.assertTrue(behavior.get("Condition").startswith(
                    "#{mascot.environment.floor.isOn(mascot.anchor) && "))
                self.assertNotIn("activeIE", behavior.get("Condition"))
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


STOCK_OR_FREE = {"Walk", "Run", "Idle", "Stretch", "SitAndFaceMouse",
                 "HugAffordance", "HugSearch", "Trip"}


class CrewDesynchronisationTests(unittest.TestCase):
    """The four mascots must not perform the same kind of move at once."""

    def setUp(self):
        import sys
        from pathlib import Path
        tools = str(Path(__file__).resolve().parents[1] / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import ava_common
        self.spec = ava_common

    def test_each_character_gets_a_different_quarter_cycle_slot(self):
        phases = [self.spec.SLOT_PHASE[char] for char in CHARS]
        self.assertEqual(len(set(phases)), 4)
        self.assertEqual(sorted(phases), [0, 1, 2, 3])

    def test_no_two_characters_are_offered_the_same_activity_class(self):
        slots = sorted(self.spec.SLOT_OF_CLASS.values())
        self.assertEqual(slots, [0, 1, 2, 3])
        for tick in range(0, 4000, 3):
            classes = {}
            for char in CHARS:
                phase = self.spec.SLOT_PHASE[char]
                current = (tick // self.spec.SLOT_TICKS + phase) % 4
                classes.setdefault(current, []).append(char)
            self.assertEqual(max(len(v) for v in classes.values()), 1,
                             f"two characters shared a slot at tick {tick}")

    def test_every_character_still_reaches_every_activity_class(self):
        for char in CHARS:
            seen = set()
            for tick in range(self.spec.SLOT_TICKS * 8):
                seen.add((tick // self.spec.SLOT_TICKS
                          + self.spec.SLOT_PHASE[char]) % 4)
            self.assertEqual(seen, {0, 1, 2, 3})

    def test_grouped_behaviours_are_slotted_and_never_repeat_immediately(self):
        for char in CHARS:
            with self.subTest(char=char):
                _, _, behaviors = MascotAnimationRegressionTests().read_pack(char)
                # Only the behaviours this pack generates are ours to tune;
                # the original pack's own routes (walk, sit, hug) are left
                # alone so the crew still behaves like the stock mascots.
                mine = set(self.spec.ACTIONS) | set(self.spec.SEQUENCES)
                seen = 0
                for behavior in behaviors.iter(f"{{{NS['m']}}}Behavior"):
                    name = behavior.get("Name")
                    if name not in mine or name == "Dance" or behavior.get("Frequency") == "0":
                        continue
                    self.assertIn("getBehavior()", behavior.get("Condition") or "",
                                  f"{char}/{name} can be replayed back to back")
                    if self.spec.activity_slot(name) is not None:
                        self.assertIn("getTime()", behavior.get("Condition") or "",
                                      f"{char}/{name} is not crew-slotted")
                    seen += 1
                self.assertGreater(seen, 10)

    def test_walking_and_breathing_are_not_locked_to_a_slot(self):
        _, _, behaviors = MascotAnimationRegressionTests().read_pack("Blue")
        for name in ("Walk", "Run", "Idle", "Stretch"):
            self.assertIsNone(self.spec.activity_slot(name),
                              f"{name} must stay available all the time")
            entry = next((b for b in behaviors.iter(f"{{{NS['m']}}}Behavior")
                          if b.get("Name") == name), None)
            if entry is not None:
                self.assertNotIn("getTime", entry.get("Condition") or "",
                                 f"{name} must not be crew-slotted")


class FigureScaleTests(unittest.TestCase):
    """A character must not change size when it changes animation."""

    def test_every_character_uses_one_figure_scale(self):
        import sys
        from pathlib import Path
        tools = str(Path(__file__).resolve().parents[1] / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import normalize_stock_art as art
        measured = art.measure_characters()
        for char, (ratio, count) in measured.items():
            with self.subTest(char=char):
                self.assertGreater(count, 50)
                self.assertAlmostEqual(
                    ratio, 1.0, delta=art.SCALE_TOLERANCE,
                    msg=f"{char}'s original-pack art is {ratio:.3f}x the shared "
                        f"original, so {char} changes size between animations")


if __name__ == "__main__":
    unittest.main()
