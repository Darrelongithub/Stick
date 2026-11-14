#!/usr/bin/env python3
"""Produce source-annotated body-ratio evidence; never modifies pack art."""
import json
import math
from pathlib import Path
import cv2
from PIL import Image, ImageDraw
import stickgen

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = json.loads((ROOT/'tools/reference_proportions.json').read_text())
    capture = cv2.VideoCapture(str(ROOT/spec['video']))
    capture.set(cv2.CAP_PROP_POS_MSEC, spec['seconds']*1000)
    ok, bgr = capture.read()
    if not ok:
        raise RuntimeError('Could not decode annotated reference timestamp')
    source = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    out = ROOT/'docs/proportions'
    out.mkdir(exist_ok=True)
    sheet = Image.new('RGB', (1000, 760), '#202630')
    draw = ImageDraw.Draw(sheet)
    stats = {}
    for col, (char, points) in enumerate(spec['characters'].items()):
        x = col*250
        draw.text((x+10, 8), char, fill='white')
        crop = source.crop(points['crop'])
        # Same shot scale for ALL four: retain Orange's genuinely larger head.
        crop = crop.resize((round(crop.width*.32), round(crop.height*.32)), Image.Resampling.LANCZOS)
        sheet.paste(crop, (x+60, 30))
        draw.text((x+10, 255), 'Video 10s, common 0.32x scale', fill='white')
        annotated = source.crop(points['crop'])
        d = ImageDraw.Draw(annotated)
        left, top = points['crop'][:2]
        for key in ('head', 'shoulder', 'hip', 'elbow', 'hand', 'knee', 'foot'):
            px, py = points[key]; px-=left;py-=top
            d.ellipse((px-2,py-2,px+2,py+2), fill='white')
        annotated.save(out/f'{char.lower()}-reference-joints.png')
        height = points['foot'][1]-(points['head'][1]-points['radius'])
        head = 2*points['radius']
        distance = lambda a,b: math.dist(points[a], points[b])
        stats[char] = {
            'head_diameter_over_visible_height': round(head/height,3),
            'head_center_to_shoulder_in_head_diameters': round(distance('head','shoulder')/head,3),
            'torso_in_head_diameters': round(distance('shoulder','hip')/head,3),
            'arm_centerline_in_head_diameters': round((distance('shoulder','elbow')+distance('elbow','hand'))/head,3),
            'leg_centerline_in_head_diameters': round((distance('hip','knee')+distance('knee','foot'))/head,3),
        }
        for row, filename in enumerate(('stand01.png','idle01.png','wall_climb_smooth01.png')):
            image = Image.open(ROOT/'AVA Shimejis'/char/filename).convert('RGBA')
            image = image.resize((image.width,image.height),Image.Resampling.NEAREST)
            yy = 290+row*155
            sheet.paste(image,(x+45,yy),image)
            draw.text((x+10,yy+137),filename,fill='white')
    sheet.save(out/'family-audit.png')
    p = stickgen.PROPORTIONS
    diameter = 2*stickgen.HEAD_R
    stats['current_generated_rig'] = {
        'head_center_to_shoulder_in_head_diameters': round((p['neck']+p['neck-shoulder'])/diameter,3),
        'torso_in_head_diameters': round(p['torso']/diameter,3),
        'arm_centerline_in_head_diameters': round((p['upper arm']+p['forearm'])/diameter,3),
        'leg_centerline_in_head_diameters': round((p['thigh']+p['shin'])/diameter,3),
    }
    (out/'measurements.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(json.dumps(stats,indent=2))


if __name__ == '__main__':
    main()
