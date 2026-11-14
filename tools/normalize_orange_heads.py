#!/usr/bin/env python3
"""Apply reviewed Orange head interiors without redrawing poses or props.

The region manifest now covers legacy stock images only. Procedural frames
render a larger ring directly. Source climbing and video images are untouched.
Run this AFTER regenerating stock/procedural art. No runtime dependency.
"""
import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REGIONS = json.loads(Path(__file__).with_name('orange_head_regions.json').read_text())


def hollow(image, x, y, radius):
    """Cut a transparent, antialiased interior; preserve the outer silhouette.

    Retain a ~3.5px ring, matching the narrowest source-art head outline.
    Minimum with existing alpha makes reruns byte-identical and avoids filling
    any preexisting transparent pixels. RGB, canvas and exterior stay unchanged.
    """
    a = np.array(image.convert('RGBA'))
    yy, xx = np.indices(a.shape[:2])
    distance = np.hypot(xx-x, yy-y)
    keep = np.clip(distance-(radius-3.5)+.5, 0, 1)
    a[:, :, 3] = np.minimum(a[:, :, 3], np.rint(keep*255).astype('uint8'))
    return Image.fromarray(a)


def normalize(image, filename):
    region = next((r for r in REGIONS if r[0] == filename), None)
    if not region:
        return image
    _, x, y, _ = region
    a = np.array(image.convert('RGBA'))
    # Source Orange outer diameter is 1.5x a solid-head character's diameter.
    # Two old bounce frames have the head close to the canvas bottom: shift
    # its center up 2px rather than clipping a newly enlarged outline.
    x = min(max(x, 20), image.width-21)
    y = min(max(y, 20), image.height-21)
    yy, xx = np.indices(a.shape[:2])
    distance = np.hypot(xx-x, yy-y)
    outer = np.clip(18.5-distance, 0, 1)
    interior = np.clip(distance-12.5, 0, 1)
    ring = np.rint(outer*interior*255).astype('uint8')
    added = ring > a[:, :, 3]
    a[added, :3] = (242, 111, 36)
    a[:, :, 3] = np.minimum(np.maximum(a[:, :, 3], ring),
                            np.rint(interior*255).astype('uint8'))
    return Image.fromarray(a)


def main():
    changed = 0
    for name, x, y, radius in REGIONS:
        path = ROOT/'AVA Shimejis/Orange'/name
        with Image.open(path) as source:
            original = source.convert('RGBA')
        result = normalize(original, name)
        if result.tobytes() != original.tobytes():
            result.save(path)
            changed += 1
    print(f'Orange hollow heads: {changed} updated / {len(REGIONS)} reviewed regions')


if __name__ == '__main__':
    main()
