#!/usr/bin/env python3
"""Adapt original artwork with motion-compensated in-betweens at native 25Hz.

Exact source poses remain at their original tick boundaries. Duration, integer
velocity and total displacement are unchanged; no skeleton is regenerated.
"""
import json
import shutil
from pathlib import Path
from PIL import Image
from motion_smoothing import tween

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'third_party/alan-stickfigures'


def main():
    data=json.loads((SOURCE/'source.json').read_text());result={}
    for char,actions in data['characters'].items():
        names={p['Image'].lstrip('/') for poses in actions.values() for p in poses}
        images={n:Image.open(SOURCE/char/n).convert('RGBA') for n in names}
        scale=min(1.,128/max(max(im.size) for im in images.values()))
        dest=ROOT/'AVA Shimejis'/char
        shutil.copy2(SOURCE/'LICENSE',dest/'classic_climbing_LICENSE.txt')
        adapted_images={}
        for n,im in images.items():
            size=(round(im.width*scale),round(im.height*scale))
            resized=im.resize(size,Image.Resampling.LANCZOS) if size!=im.size else im
            canvas=Image.new('RGBA',(160,160));canvas.alpha_composite(resized,(16,16))
            adapted_images[n]=canvas
        cd={};keys={}
        for name,poses in actions.items():
            adapted=[];keyframes=[]
            prefix='wall_climb' if name=='ClimbWall' else 'swing'
            for i,p in enumerate(poses):
                source_name=p['Image'].lstrip('/')
                following=poses[(i+1)%len(poses)]
                x,y=map(int,p['ImageAnchor'].split(','))
                nx,ny=map(int,following['ImageAnchor'].split(','))
                vx,vy=map(int,p['Velocity'].split(','))
                def velocity(v):
                    return (1 if v>0 else -1)*max(1,round(abs(v)*scale)) if v else 0
                duration=int(p['Duration'])
                for tick in range(duration):
                    amount=tick/duration
                    image=tween(adapted_images[source_name],adapted_images[following['Image'].lstrip('/')],amount)
                    filename=f'{prefix}_smooth{len(adapted)+1:02d}.png'
                    image.save(dest/filename)
                    anchor=f'{16+round((x+(nx-x)*amount)*scale)},{16+round((y+(ny-y)*amount)*scale)}'
                    adapted.append((filename,anchor,f'{velocity(vx)},{velocity(vy)}',1))
                    if tick==0:keyframes.append({'file':filename,'source':source_name})
            cd[name]=adapted;keys[name]=keyframes
        for hold,move,index,prefix in [('GrabWall','ClimbWall',0,'wall_hold'),('GrabCeiling','ClimbCeiling',2,'hang')]:
            source_pose=actions[move][index]
            x,y=map(int,source_pose['ImageAnchor'].split(','))
            filename=prefix+'01.png';adapted_images[source_pose['Image'].lstrip('/')].save(dest/filename)
            cd[hold]=[(filename,f'{16+round(x*scale)},{16+round(y*scale)}','0,0',12)]
        result[char]={'scale':scale,'actions':cd,'keyframes':keys}
        keep={p[0] for poses in cd.values() for p in poses}
        for prefix in ['wall_climb','swing','wall_hold','hang']:
            for path in dest.glob(prefix+'*.png'):
                if path.name not in keep:path.unlink()
    (ROOT/'tools/classic_climbing.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Built 15 wall ticks and 16 ceiling ticks per character, with exact source key poses')

if __name__=='__main__':main()
