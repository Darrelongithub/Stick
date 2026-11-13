#!/usr/bin/env python3
"""Build finite video-derived additions from reviewed extraction PNGs.

Requires Pillow, NumPy, SciPy. Run extract_reference_motion.py first with the
commands in docs/video-motion-catalogue.md. Never touches stock interaction art.
Temporal signed-distance interpolation avoids double-image alpha crossfades.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
from motion_smoothing import stabilize

ROOT = Path(__file__).resolve().parents[1]
CLIPS = [
    ('Orange','orange-step','VideoLeanStep',31,34.3),
    ('Orange','orange-step','VideoKneeLift',34.3,35),
    ('Green','green-reach','VideoRaiseArms',134,134.5),
    ('Green','green-reach','VideoReach',134.5,135.5),
    ('Blue','blue-reach','VideoReach',150,150.75),
    ('Blue','blue-reach','VideoLean',150.75,151.5),
    ('Yellow','yellow-step','VideoStep',156,156.6),
    ('Yellow','yellow-step','VideoLean',156.6,157.2),
]
COLORS = {'Orange':(242,111,36),'Green':(95,183,0),'Blue':(37,192,255),'Yellow':(255,197,0)}


def signed(mask):
    return ndimage.distance_transform_edt(mask)-ndimage.distance_transform_edt(~mask)


def main():
    result = []
    for char, clip, name, start, end in CLIPS:
        source = ROOT/'preview/reference'/clip
        meta = json.loads((source/'source.json').read_text())
        if meta.get('mask_boundary_frames'):
            raise RuntimeError(f'{clip}: clipped masks must be repaired before build')
        records = meta['frames']
        raw = [Image.open(source/r['file']).convert('RGBA') for r in records]
        # Keep one scale for the entire shot, not a different scale per pose.
        # Normalize source silhouette height to the legacy pack body envelope.
        bounds = [im.getbbox() for im in raw]
        max_height = max(b[3]-b[1] for b in bounds)
        scale = 110/max_height
        floor = max(b[3] for b in bounds)
        fields = []
        for im,b in zip(raw,bounds):
            # Root translation is removed; retain internal pose deformation.
            cx = (b[0]+b[2])/2
            width,height = round(im.width*scale),round(im.height*scale)
            alpha = im.getchannel('A').resize((width,height),Image.Resampling.LANCZOS)
            canvas = Image.new('L',(160,160))
            canvas.paste(alpha,(round(80-cx*scale),round(144-floor*scale)))
            mask = np.asarray(canvas) > 96
            fields.append(signed(mask))
        times = np.array([r['source_seconds'] for r in records])
        count = math.ceil((end-start)/.04)
        frames, preview = [], []
        prefix = 'videoref_'+name.lower()+'_'
        dest = ROOT/'AVA Shimejis'/char
        for old in dest.glob(prefix+'*.png'):
            old.unlink()
        for i in range(count):
            t = min(start+i*.04, times[-1])
            right = min(int(np.searchsorted(times,t,side='right')),len(times)-1)
            left = max(0,right-1)
            span = times[right]-times[left]
            mix = min(1,max(0,(t-times[left])/span)) if span else 0
            field = fields[left]*(1-mix)+fields[right]*mix
            # Smooth subpixel contour coverage, not a ghosted RGB blend.
            alpha = np.clip((field+.5)*255,0,255).astype('uint8')
            sprite = Image.new('RGBA',(160,160),(*COLORS[char],0))
            sprite.putalpha(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(.25)))
            bbox=sprite.getbbox()
            if not bbox or min(bbox[0],bbox[1],160-bbox[2],160-bbox[3]) < 8:
                raise RuntimeError(f'{char}/{name}/{i}: unsafe sprite margins {bbox}')
            filename=f'{prefix}{i+1:03d}.png'
            sprite.save(dest/filename); frames.append(filename)
            bg=Image.new('RGBA',(160,160),'#202630'); bg.alpha_composite(sprite)
            preview.append(bg.convert('RGB').resize((320,320),Image.Resampling.NEAREST))
        source_sprites = [Image.open(dest/name).convert('RGBA') for name in frames]
        cleaned = stabilize(source_sprites)
        preview = []
        for name, sprite in zip(frames, cleaned):
            sprite.save(dest/name)
            bg = Image.new('RGBA', (160,160), '#202630'); bg.alpha_composite(sprite)
            preview.append(bg.convert('RGB').resize((320,320), Image.Resampling.LANCZOS))
        out = ROOT/'preview/reference/finished';out.mkdir(parents=True,exist_ok=True)
        # No loop extension: a fresh viewer plays this once and leaves the last pose.
        preview[0].save(out/f'{char}-{name}.gif',save_all=True,append_images=preview[1:],duration=40)
        result.append({'character':char,'name':name,'source_interval':[start,end],
                       'source_clip':clip,'frames':frames,'tick_ms':40,'loop':False})
    manifest = {'source':'output.mp4','sha256':hashlib.sha256((ROOT/'output.mp4').read_bytes()).hexdigest(),
                'method':'source silhouette, fixed shot scale, horizontal recenter, signed-distance 25Hz resampling',
                'actions':result}
    (ROOT/'tools/video_actions.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Built {len(result)} finite actions / {sum(len(a["frames"]) for a in result)} frames')


if __name__=='__main__':
    main()
