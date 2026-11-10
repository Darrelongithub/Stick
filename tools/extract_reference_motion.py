#!/usr/bin/env python3
"""Shot-specific reference-motion prototype from output.mp4, not a pack installer.

The default interval is an exaggerated stepping/leaning action, NOT a walk
loop. Fixed crop/scale preserves relative pose size and motion. Color keying is
specific to selected character colors and manually reviewed shot regions; do not use on other shots
without reviewing every mask. Outputs remain under ignored preview/.
"""
import argparse
import json
from pathlib import Path
import av
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', type=Path, default=Path('output.mp4'))
    p.add_argument('--out', type=Path, default=Path('preview/reference/orange-step'))
    p.add_argument('--start', type=float, default=31)
    p.add_argument('--end', type=float, default=35)
    p.add_argument('--character', choices=['Orange', 'Blue', 'Green', 'Yellow', 'Red'], default='Orange')
    p.add_argument('--roi', type=float, nargs=4, metavar=('LEFT','TOP','RIGHT','BOTTOM'),
                   help='Normalized shot-specific mask bounds, 0..1')
    a = p.parse_args()
    if a.roi and not (0 <= a.roi[0] < a.roi[2] <= 1 and 0 <= a.roi[1] < a.roi[3] <= 1):
        p.error('roi must be ordered normalized bounds within 0..1')
    if a.end <= a.start:
        p.error('end must be after start')
    samples = []
    boundary_frames = []
    with av.open(str(a.video)) as c:
        stream = c.streams.video[0]
        c.seek(int(a.start / stream.time_base), stream=stream)
        for f in c.decode(stream):
            if f.time is None:
                continue
            t = float(f.time)
            if t < a.start:
                continue
            if t >= a.end:
                break
            rgb = np.asarray(f.to_image())
            r, g, b = [rgb[:, :, k].astype(float) for k in range(3)]
            masks = {
                'Orange': (r > 190) & (g > 65) & (g < 190) & (b < 80) & (r > g * 1.4),
                'Green': (g > 110) & (r > 30) & (r < 140) & (b < 70) & (g > r * 1.4),
                'Blue': (b > 190) & (g > 170) & (r > 10) & (r < 100) & (g > b * .65),
                'Yellow': (r > 200) & (g > 150) & (b < 70) & (r < g * 1.6),
                'Red': (r > 150) & (g < 65) & (b < 65),
            }
            mask = masks[a.character]
            roi = a.roi or [0, 0, 1, .84]
            height, width = mask.shape
            left, top, right, bottom = [round(v*n) for v,n in zip(roi,[width,height,width,height])]
            mask[:top] = False; mask[bottom:] = False
            mask[:, :left] = False; mask[:, right:] = False
            labels, count = ndimage.label(mask)
            if count:
                areas = np.bincount(labels.ravel()); areas[0] = 0
                mask = labels == areas.argmax()
            if (mask[top, left:right].any() or mask[bottom-1, left:right].any()
                    or mask[top:bottom, left].any() or mask[top:bottom, right-1].any()):
                boundary_frames.append(t)
            yy, xx = np.nonzero(mask)
            if not len(xx):
                raise RuntimeError(f'No {a.character} silhouette at {t:.3f}s')
            rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
            rgba[:, :, :3] = {'Orange': (242,111,36), 'Blue': (37,192,255),
                                'Green': (95,183,0), 'Yellow': (255,197,0), 'Red': (220,0,0)}[a.character]
            rgba[:, :, 3] = mask.astype(np.uint8) * 255
            samples.append((t, Image.fromarray(rgba), (xx.min(), yy.min(), xx.max()+1, yy.max()+1)))
    if not samples:
        raise RuntimeError('No frames in interval')
    bounds = (min(x[2][0] for x in samples), min(x[2][1] for x in samples),
              max(x[2][2] for x in samples), max(x[2][3] for x in samples))
    w, h = bounds[2]-bounds[0], bounds[3]-bounds[1]
    scale = min(224/w, 224/h)
    size = (round(w*scale), round(h*scale))
    a.out.mkdir(parents=True, exist_ok=True)
    previews = []
    records = []
    for i, (t, im, _) in enumerate(samples):
        sprite = Image.new('RGBA', (256, 256))
        sprite.alpha_composite(im.crop(bounds).resize(size, Image.Resampling.LANCZOS),
                               ((256-size[0])//2, 240-size[1]))
        sprite.save(a.out / f'frame-{i:03d}.png')
        bg = Image.new('RGBA', sprite.size, '#202630')
        bg.alpha_composite(sprite)
        previews.append(bg.convert('RGB'))
        records.append({'file': f'frame-{i:03d}.png', 'source_seconds': t})
    durations = [round(1000*(samples[i+1][0]-t)) if i+1 < len(samples) else 42
                 for i, (t, _, _) in enumerate(samples)]
    previews[0].save(a.out / 'motion.gif', save_all=True, append_images=previews[1:],
                     duration=durations)
    sheet = Image.new('RGB', (256*4, 280*3), '#202630')
    draw = ImageDraw.Draw(sheet)
    for j, i in enumerate(np.linspace(0, len(samples)-1, 12, dtype=int)):
        x, y = j%4*256, j//4*280
        sheet.paste(previews[i], (x,y))
        draw.text((x+8,y+258), f'{samples[i][0]:.3f}s', fill='white')
    sheet.save(a.out / 'poses.png')
    (a.out / 'source.json').write_text(json.dumps({
        'video': str(a.video), 'character': a.character, 'roi': a.roi, 'interval': [a.start, a.end], 'crop': [int(v) for v in bounds],
        'scale': scale, 'method': 'largest connected character color mask, fixed crop and scale; no pose synthesis',
        'limitations': 'hard color key; no live host validation; not a neutral walk or seamless loop',
        'mask_boundary_frames': boundary_frames, 'frames': records}, indent=2)+'\n')
    if boundary_frames:
        print(f'REVIEW REQUIRED: {len(boundary_frames)} frames touch ROI boundary; possible clipping')
    print(f'{len(samples)} source frames extracted to {a.out}; fixed crop {bounds}')


if __name__ == '__main__':
    main()
