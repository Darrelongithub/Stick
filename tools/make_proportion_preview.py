#!/usr/bin/env python3
"""Native-canvas redraw comparison and one-pass pose animation (not host capture)."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CHARS = ['Blue', 'Orange', 'Yellow', 'Green']


def main():
    out = ROOT/'docs/proportions'
    names = ['stand01.png', 'idle01.png', 'crawl01.png', 'fall01.png', 'wall_climb_smooth01.png']
    sheet = Image.new('RGB', (960, 1100), '#202630')
    draw = ImageDraw.Draw(sheet)
    for col, char in enumerate(CHARS):
        for row, name in enumerate(names):
            image = Image.open(ROOT/'AVA Shimejis'/char/name).convert('RGBA')
            canvas = Image.new('RGBA', (160,160))
            canvas.alpha_composite(image, ((160-image.width)//2,160-image.height))
            image = canvas.resize((200,200), Image.Resampling.LANCZOS)
            sheet.paste(image, (col*240,row*220+15), image)
            draw.text((col*240,row*220), char+' '+name, fill='white')
    sheet.save(out/'redrawn-families.png')
    frames = []
    for tick in range(48):
        bg = Image.new('RGB', (640,480), '#202630')
        for col, char in enumerate(CHARS):
            for row, prefix in enumerate(['idle','crawl','fall']):
                paths = sorted((ROOT/'AVA Shimejis'/char).glob(prefix+'[0-9][0-9].png'))
                image = Image.open(paths[tick%len(paths)]).convert('RGBA')
                bg.paste(image,(col*160,row*160),image)
        frames.append(bg)
    frames[0].save(out/'redrawn-motion.gif',save_all=True,append_images=frames[1:],duration=40)


if __name__ == '__main__':
    main()
