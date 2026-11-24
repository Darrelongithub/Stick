#!/usr/bin/env python3
"""Build an offline pack copy sharing pixel-identical, same-anchor image refs.

No pixels, timing, anchors or behavior choices change. Source files are never
modified. ShimeLinux caches by image path, so identical PNGs under different
names otherwise occupy separate left/right pixel arrays. Requires Pillow.
"""
import argparse
from collections import defaultdict
import hashlib
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from PIL import Image

CHARS = ('Blue', 'Orange', 'Yellow', 'Green')


def optimize_character(root):
    """Return original-format XML bytes, aliases, and estimated saved pixels."""
    root = Path(root)
    path = root/'conf/actions.xml'
    original = path.read_bytes()
    tree = ET.fromstring(original)
    anchors = defaultdict(set)
    excluded = set()
    for node in tree.iter():
        left, right = node.get('Image'), node.get('ImageRight')
        if right:
            excluded.update(filter(None, (left, right)))
        if left:
            anchors[left].add(node.get('ImageAnchor'))
    groups = defaultdict(list)
    sizes = {}
    for ref, values in sorted(anchors.items()):
        # Restrict to local leaf PNG names and one unambiguous anchor. Do not
        # resolve external assets, symlinks or paths outside this character.
        if (ref in excluded or len(values) != 1 or None in values or
                not re.fullmatch(r'/?[A-Za-z0-9_.-]+\.png', ref, re.I)):
            continue
        image_path = root/ref.lstrip('/')
        if image_path.is_symlink():
            continue
        with Image.open(image_path) as image:
            rgba = image.convert('RGBA')
            key = (rgba.size, hashlib.sha256(rgba.tobytes()).digest(), tuple(values))
            groups[key].append(ref)
            sizes[ref] = rgba.width * rgba.height
    aliases = {}
    for refs in groups.values():
        canonical = min(refs)
        aliases.update({ref: canonical for ref in refs if ref != canonical})
    # Preserve the BOM, comments, CRLFs and all formatting. Match attributes
    # only within Pose tags; never rewrite documentation or action names.
    def pose(match):
        tag = match.group(0)
        if tag.startswith((b'<!--', b'<![CDATA[')):
            return tag
        def attribute(attr):
            old = attr.group(2).decode('utf-8')
            new = aliases.get(old, old).encode('utf-8')
            return attr.group(1) + new + attr.group(3)
        return re.sub(rb'(\sImage\s*=\s*[\'"])([^\'"]+)([\'"])', attribute, tag)
    updated = re.sub(rb'<!--.*?-->|<!\[CDATA\[.*?\]\]>|<(?:\w+:)?Pose\b[^>]*>',
                     pose, original, flags=re.DOTALL)
    ET.fromstring(updated)
    return updated, aliases, sum(sizes[ref] for ref in aliases)


def build(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('output must be separate from the source tree')
    if output.exists():
        raise ValueError('output already exists; choose a new directory')
    # Validate/plan all characters before creating output. Never alter a live
    # installation; callers explicitly choose whether to deploy this copy.
    plans = {char: optimize_character(source/char) for char in CHARS}
    shutil.copytree(source, output)
    report = {}
    for char, (xml, aliases, pixels) in plans.items():
        (output/char/'conf/actions.xml').write_bytes(xml)
        report[char] = {'aliased_paths': len(aliases),
                        'estimated_two_direction_bytes_saved_at_1x': pixels * 8}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build(args.source, args.output)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f'{error}\n')
    total = 0
    for char, info in report.items():
        saved = info['estimated_two_direction_bytes_saved_at_1x']
        total += saved
        print(f'{char}: {info["aliased_paths"]} redundant paths; {saved / 2**20:.2f} MiB pixel-array saving at 1x')
    print(f'Total estimate: {total / 2**20:.2f} MiB; not a measured RSS reduction.')
    print(f'Offline output: {args.output}; source unchanged; nothing installed or started.')


if __name__ == '__main__':
    main()
