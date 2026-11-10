#!/usr/bin/env python3
"""Decode the whole reference into timestamped review sheets (not motion extraction)."""
import argparse
import json
from pathlib import Path
import av
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', type=Path, default=Path('output.mp4'))
    p.add_argument('--out', type=Path, default=Path('preview/reference/full'))
    p.add_argument('--step', type=float, default=2)
    a = p.parse_args()
    if a.step <= 0:
        p.error('step must be positive')
    a.out.mkdir(parents=True, exist_ok=True)
    rows, tiles, decoded, target, last = [], [], 0, 0., 0.
    with av.open(str(a.video)) as c:
        s = c.streams.video[0]
        fps = str(s.average_rate)
        for frame in c.decode(s):
            decoded += 1
            if frame.time is None:
                continue
            last = float(frame.time)
            if last + 1e-6 < target:
                continue
            im = frame.to_image()
            filename = f'{last:09.3f}.jpg'
            im.save(a.out / filename, quality=88)
            im.thumbnail((384,216))
            tiles.append((last, im))
            rows.append({'time': last, 'file': filename})
            target += a.step
    sheets = []
    for offset in range(0,len(tiles),24):
        sheet = Image.new('RGB',(384*4,240*6),'#202630')
        d = ImageDraw.Draw(sheet)
        for j,(time,im) in enumerate(tiles[offset:offset+24]):
            x,y=j%4*384,j//4*240
            sheet.paste(im,(x,y));d.text((x+6,y+218),f'{time:.3f}s',fill='white')
        name=f'overview-{offset//24+1:02d}.jpg'
        sheet.save(a.out/name,quality=90);sheets.append(name)
    (a.out/'index.json').write_text(json.dumps({'video':str(a.video),'decoded_frames':decoded,
        'last_frame_seconds':last,'fps':fps,'sample_interval_seconds':a.step,
        'note':'All frames decoded; visual sheets sampled, not a claim of frame-by-frame review.',
        'sheets':sheets,'samples':rows},indent=2)+'\n')
    print(f'{decoded} frames decoded through {last:.3f}s; {len(rows)} samples, {len(sheets)} sheets')


if __name__=='__main__':
    main()
