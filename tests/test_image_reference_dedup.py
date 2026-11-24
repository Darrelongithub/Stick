"""Lossless offline image-reference sharing; no engine or desktop required."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dedup', ROOT/'tools/deduplicate_image_refs.py')
dedup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dedup)


class ImageReferenceDedupTests(unittest.TestCase):
    def test_real_pack_preserves_every_pose_pixel_anchor_timing_and_other_attribute(self):
        total = 0
        for char in dedup.CHARS:
            root = ROOT/'AVA Shimejis'/char
            before = (root/'conf/actions.xml').read_bytes()
            after, aliases, pixels = dedup.optimize_character(root)
            self.assertEqual((root/'conf/actions.xml').read_bytes(), before)
            old_nodes = list(ET.fromstring(before).iter())
            new_nodes = list(ET.fromstring(after).iter())
            self.assertEqual(len(old_nodes), len(new_nodes))
            checked = set()
            for old, new in zip(old_nodes, new_nodes):
                self.assertEqual(old.tag, new.tag)
                self.assertEqual(old.text, new.text)
                self.assertEqual(old.tail, new.tail)
                a, b = dict(old.attrib), dict(new.attrib)
                left, right = a.pop('Image', None), b.pop('Image', None)
                self.assertEqual(a, b)
                self.assertEqual(left is None, right is None)
                if left != right and (left, right) not in checked:
                    checked.add((left, right))
                    with Image.open(root/left.lstrip('/')) as x, Image.open(root/right.lstrip('/')) as y:
                        self.assertEqual(x.size, y.size)
                        self.assertEqual(x.convert('RGBA').tobytes(), y.convert('RGBA').tobytes())
            self.assertEqual(set(aliases.items()), checked)
            self.assertGreater(pixels, 0)
            total += pixels * 8
        self.assertGreater(total, 60 * 2**20)

    def test_comments_ambiguous_anchors_and_explicit_right_images_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'conf').mkdir()
            for name in ('a', 'b', 'c', 'd', 'e'):
                Image.new('RGBA', (2, 2), 'red').save(root/f'{name}.png')
            xml = b'''<Mascot><!-- <Pose Image="/b.png"/> -->
<Pose Image="/a.png" ImageAnchor="1,1"/>
<Pose Image="/b.png" ImageAnchor="1,1"/>
<Pose Image="/c.png" ImageAnchor="1,1"/>
<Pose Image="/c.png" ImageAnchor="2,2"/>
<Pose Image="/d.png" ImageRight="/e.png" ImageAnchor="1,1"/>
</Mascot>'''
            (root/'conf/actions.xml').write_bytes(xml)
            output, aliases, pixels = dedup.optimize_character(root)
            self.assertEqual(aliases, {'/b.png': '/a.png'})
            self.assertEqual(pixels, 4)
            self.assertIn(b'<!-- <Pose Image="/b.png"/> -->', output)
            self.assertIn(b'Image="/c.png" ImageAnchor="2,2"', output)
            self.assertIn(b'Image="/d.png" ImageRight="/e.png"', output)
            (root/'conf/actions.xml').write_bytes(output)
            again, aliases, _ = dedup.optimize_character(root)
            self.assertEqual(aliases, {})
            self.assertEqual(again, output)

    def test_existing_or_overlapping_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for output in (root, root/'child', root.parent):
                with self.assertRaises(ValueError):
                    dedup.build(root, output)
            source, target = root/'source', root/'target'
            source.mkdir()
            target.mkdir()
            with self.assertRaises(ValueError):
                dedup.build(source, target)

    def test_build_copies_pixels_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'source', Path(directory)/'output'
            for char in dedup.CHARS:
                root = source/char
                (root/'conf').mkdir(parents=True)
                (root/'conf/actions.xml').write_bytes(
                    b'<Mascot><Pose Image="/a.png" ImageAnchor="1,1"/>'
                    b'<Pose Image="/b.png" ImageAnchor="1,1"/></Mascot>')
                for name in ('a', 'b'):
                    Image.new('RGBA', (2, 2), 'red').save(root/f'{name}.png')
            originals = {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
            report = dedup.build(source, output)
            self.assertEqual(sum(r['aliased_paths'] for r in report.values()), 4)
            for relative, content in originals.items():
                self.assertEqual((source/relative).read_bytes(), content)
                if relative.suffix == '.png':
                    self.assertEqual((output/relative).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
