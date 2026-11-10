#!/usr/bin/env python3
"""Extract timestamped evidence from the tracked reference, without modifying art.

Requires Pillow and PyAV. Output is deliberately gitignored under preview/.
Example: python tools/sample_reference.py --start 30 --step .125 --count 24
"""
import argparse
from pathlib import Path
import av
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', type=Path, default=Path(__file__).resolve().parents[1] / 'output.mp4')
    p.add_argument('--start', type=float, default=30)
    p.add_argument('--step', type=float, default=.125)
    p.add_argument('--count', type=int, default=24)
    p.add_argument('--out', type=Path, default=Path('preview/reference'))
    a = p.parse_args()
    if a.start < 0 or a.step <= 0 or not 1 <= a.count <= 240:
        p.error('start must be nonnegative, step positive, count 1..240')
    a.out.mkdir(parents=True, exist_ok=True)
    samples = []
    with av.open(str(a.video)) as c:
        s = c.streams.video[0]
        for i in range(a.count):
            target = a.start + i * a.step
            c.seek(int(target / s.time_base), stream=s)
            for f in c.decode(s):
                if f.time is not None and float(f.time) >= target:
                    im = f.to_image()
                    actual = float(f.time)
                    im.save(a.out / f'{actual:09.3f}.png')
                    im.thumbnail((480, 270))
                    samples.append((actual, im))
                    break
            else:
                break
    if not samples:
        raise SystemExit('No frames found at requested timestamps')
    sheet = Image.new('RGB', (480 * 4, 294 * ((len(samples) + 3) // 4)), '#242424')
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(samples):
        x, y = (i % 4) * 480, (i // 4) * 294
        sheet.paste(im, (x, y))
        d.text((x + 8, y + 273), f'{t:.3f}s', fill='white')
    dest = a.out / f'sequence-{a.start:g}.jpg'
    sheet.save(dest)
    print(f'{len(samples)} timestamped frames: {dest}')


if __name__ == '__main__':
    main()
