#!/usr/bin/env python3
"""One-pass previews of installed source-climbing and finite video actions."""
from pathlib import Path
import json
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]


def preview_climbing():
    data=json.loads((ROOT/'tools/classic_climbing.json').read_text());frames=[]
    for tick in range(16):
        sheet=Image.new('RGBA',(800,450),'#252b34');d=ImageDraw.Draw(sheet)
        for col,(char,entry) in enumerate(data.items()):
            x=col*200;d.text((x+8,5),char,fill='white')
            for row,action in enumerate(['ClimbWall','ClimbCeiling']):
                poses=entry['actions'][action]
                timeline=[p for p in poses for _ in range(p[3])]
                name,anchor,_,_=timeline[min(tick,len(timeline)-1)]
                ax,ay=map(int,anchor.split(','))
                im=Image.open(ROOT/'AVA Shimejis'/char/name).convert('RGBA')
                if row==0:
                    d.line((x+24,25,x+24,215),fill='#8998a8',width=2);pos=(x+24-ax,205-ay)
                else:
                    d.line((x+8,250,x+190,250),fill='#8998a8',width=2);pos=(x+105-ax,250-ay)
                sheet.alpha_composite(im,pos)
        frames.append(sheet.convert('RGB'))
    frames[0].save(ROOT/'docs/source-climbing.gif',save_all=True,append_images=frames[1:],duration=40)


def preview_video():
    actions=json.loads((ROOT/'tools/video_actions.json').read_text())['actions'];frames=[]
    for tick in range(max(len(a['frames']) for a in actions)+15):
        sheet=Image.new('RGB',(640,384),'#252b34');d=ImageDraw.Draw(sheet)
        for j,a in enumerate(actions):
            x=j%4*160;y=j//4*192
            im=Image.open(ROOT/'AVA Shimejis'/a['character']/a['frames'][min(tick,len(a['frames'])-1)]).convert('RGBA')
            sheet.paste(im,(x,y+24),im)
            d.text((x+5,y+3),a['character'],fill='white');d.text((x+5,y+15),a['name'].replace('Video',''),fill='white')
        frames.append(sheet)
    frames[0].save(ROOT/'docs/video-actions-once.gif',save_all=True,append_images=frames[1:],duration=40)


if __name__=='__main__':
    preview_climbing();preview_video()
