#!/usr/bin/env python3
"""Reproducible temporal cleanup of the eight existing video-derived actions.

Reads the immutable keyed-frame baseline, not its own previous output. Frame
count, source timing, floor anchors, source endpoints and next actions stay put.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from motion_smoothing import stabilize

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'third_party/video-motion-baseline'
    meta=json.loads((source/'source.json').read_text())
    arrays=np.load(source/'frames.npz',allow_pickle=False)
    for key,action in meta['actions'].items():
        inputs=[Image.fromarray(a) for a in arrays[key]]
        outputs=stabilize(inputs)
        for name,image in zip(action['frames'],outputs):
            box=image.getbbox()
            if not box or min(box[0],box[1],160-box[2],160-box[3])<8:
                raise RuntimeError(f'Unsafe smoothed frame {key}/{name}: {box}')
            image.save(ROOT/'AVA Shimejis'/action['character']/name)
    manifest=ROOT/'tools/video_actions.json'
    data=json.loads(manifest.read_text())
    data['smoothing']='flow-aligned neighbouring silhouette cleanup, strength .15; endpoints and timing unchanged'
    manifest.write_text(json.dumps(data,indent=2)+'\n')
    print('Smoothed eight one-shot actions; 207 frame references and XML timing unchanged')


if __name__=='__main__':main()
