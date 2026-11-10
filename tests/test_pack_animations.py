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
                # The ceiling grip sweeps only as far as a reference-length arm
                # can reach along the ceiling line, so the ceiling climb is
                # slower than the wall climb.  Velocity and pose travel must
                # still agree, or planted hands skate.
                self.assertEqual({p.get("Velocity") for p in poses}, {"0,0", "-1,0"})
                self.assertEqual(sum(int(p.get("Velocity").split(",")[0]) for p in poses), -24)
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

    def test_dance_is_a_finite_coordinated_floor_request(self):
        for char in CHARS:
            with self.subTest(char=char):
                base, actions, behaviors = self.read_pack(char)
                action = self.action(actions, "Dance")
                self.assertEqual(action.get("Type"), "Animate")
                self.assertEqual(action.get("BorderType"), "Floor")
                self.assertIn("mascot.environment.floor.isOn(mascot.anchor)", action.get("Condition"))
                self.assertNotIn("'enter'", action.get("Condition", ""))
                poses = action.findall(".//m:Pose", NS)
                self.assertTrue(poses)
                for pose in poses:
                    self.assertEqual(pose.get("Velocity"), "0,0")
                    self.assertTrue((base / pose.get("Image").lstrip("/")).is_file())
                entries = behaviors.findall('.//m:Behavior[@Name="Dance"]', NS)
                self.assertEqual(len(entries), 1)
                behavior = entries[0]
                self.assertGreater(int(behavior.get("Frequency")), 0)
                self.assertIn("mascot.environment.floor.isOn(mascot.anchor)",
                              behavior.get("Condition"))
                self.assertNotIn("activeIE", behavior.get("Condition"))
                self.assertEqual(len(behavior.findall("m:NextBehavior", NS)), 0)

    def test_generated_locomotion_is_finite_under_the_native_host(self):
        for char in CHARS:
            with self.subTest(char=char):
                _, actions, _ = self.read_pack(char)
                for name, duration in (("Walk", "48"), ("Run", "33")):
                    action = self.action(actions, name)
                    self.assertEqual(action.get("Type"), "Move")
                    self.assertEqual(action.get("Duration"), duration)

    def test_character_request_pools_have_distinct_order(self):
        orders = []
        for char in CHARS:
            _, _, behaviors = self.read_pack(char)
            generated = behaviors.find("m:BehaviorList", NS)
            import sys
            sys.path.insert(0, str(ROOT / "tools"))
            import ava_common
            owned = set(ava_common.generated_actions_for(char)) | set(ava_common.SEQUENCES)
            entries = [e for e in generated.iter(f"{{{NS['m']}}}Behavior")
                       if e.get("Name") in owned]
            names = [e.get("Name") for e in entries]
            orders.append(tuple(names))
            self.assertIn("Walk", names)
            self.assertIn("Wave", names)
            self.assertTrue(all(int(e.get("Frequency", "0")) > 0 for e in entries))
        self.assertEqual(len(set(orders)), 4)


STOCK_OR_FREE = {"Walk", "Run", "Idle", "Stretch", "SitAndFaceMouse",
                 "HugAffordance", "HugSearch", "Trip"}


class NativeTurnContractTests(unittest.TestCase):
    """The pack has no distributed lock: a patched host owns the FIFO stage."""

    def test_static_idle_and_no_script_coordinator(self):
        for char in CHARS:
            with self.subTest(char=char):
                base, actions, behaviors = MascotAnimationRegressionTests().read_pack(char)
                idle = actions.find('.//m:Action[@Name="WaitIdle"]', NS)
                self.assertIsNotNone(idle)
                self.assertEqual(idle.get("Type"), "Animate")
                poses = idle.findall('.//m:Pose', NS)
                self.assertEqual(len(poses), 1)
                self.assertEqual(poses[0].get("Velocity"), "0,0")
                self.assertEqual(poses[0].get("Duration"), "1")
                self.assertTrue((base / poses[0].get("Image").lstrip("/")).is_file())
                for name in ("AvaTurn", "AvaRelease", "AvaRested", "WaitTurn"):
                    self.assertIsNone(actions.find(f'.//m:Action[@Name="{name}"]', NS))
                    self.assertIsNone(behaviors.find(f'.//m:Behavior[@Name="{name}"]', NS))
                self.assertNotIn("Main.getProperties", Path(base / "conf/actions.xml").read_text())

    def test_native_sources_are_pinned_and_cover_every_assignment_path(self):
        base = ROOT / "linux/shimelinux"
        self.assertEqual((base / "UPSTREAM_COMMIT").read_text().strip(),
                         "b131465f5af478347009bcf6b29bad6f5579af85")
        patch = (base / "shimelinux-turns.patch").read_text()
        for path in ("Manager.kt", "Mascot.kt", "UserBehavior.kt", "Behavior.kt",
                     "TurnCoordinator.kt", "StationaryIdle.kt"):
            self.assertIn(path, patch)
        coord = (base / "overlay/src/main/kotlin/com/group_finity/mascot/TurnCoordinator.kt").read_text()
        for text in ("ArrayDeque<Request<O>>", "pending.removeFirst()",
                     "lease.request.owner === owner", "lease.token == token",
                     "require(elapsedTicks > 0)", "while (log.size > 256)"):
            self.assertIn(text, coord)
        self.assertIn("turns.pump", patch)
        self.assertIn("acknowledgeCompletedTurn", patch)
        self.assertIn('cancelUnstartedDrag()', patch)
        self.assertIn('cancelQueued(this, isDragged)', patch)
        self.assertIn('finishTurn(this, playedTicks, "drag-released")', patch)
        self.assertIn('finishTurn(this, playedTicks, "lost-ground")', patch)

    def test_pack_is_idempotent(self):
        import hashlib
        import subprocess
        import sys
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (ROOT / "AVA Shimejis").glob("*/conf/*.xml")}
        subprocess.run([sys.executable, str(ROOT / "tools/patch_xml.py"), "Blue"],
                       check=True, capture_output=True)
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (ROOT / "AVA Shimejis").glob("*/conf/*.xml")}
        self.assertEqual(before, after)


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
                # Walk/Run/Dance are now generated reference art, so fewer
                # legacy stock frames remain to measure.
                self.assertGreater(count, 10)
                self.assertAlmostEqual(
                    ratio, 1.0, delta=art.SCALE_TOLERANCE,
                    msg=f"{char}'s original-pack art is {ratio:.3f}x the shared "
                        f"original, so {char} changes size between animations")


if __name__ == "__main__":
    unittest.main()
