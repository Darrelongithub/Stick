#!/usr/bin/env python3
"""Compare every procedural frame to its own character's fixed master pose.

Also enumerate every XML-referenced raster without joint measurements. A
raster-only silhouette cannot honestly pass a bone-length test without joints.
Never equate an internally consistent rig with proven pixel-level fidelity.
"""
import csv
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import stickgen as rig
from character_reference import PROFILES, REFERENCE

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/'docs/proportions'
    rows, coverage = [], {}
    for character, target in PROFILES.items():
        measured = set()
        for action in rig.SPEC.generated_actions_for(character):
            if rig.SPEC.ACTIONS[action].get('source_authored'):
                continue
            for index, filename in enumerate(rig.SPEC.frame_names(action)):
                key = rig._anim_key_for(action, index)
                authored = rig.ANIMS[key][rig._anim_index(action, index)]
                pose = rig.normalize_pose(authored, proportions=target)
                worst = 0
                for (parent, joint), bone in rig._BONE_LENGTH.items():
                    worst = max(worst, abs(math.dist(pose[parent], pose[joint])-target[bone]))
                for near, far, parent, far_parent in rig._MIRROR:
                    bone = rig._BONE_LENGTH[(parent, near)]
                    worst = max(worst, abs(math.dist(pose[far_parent], pose[far])-target[bone]))
                rows.append({'character': character, 'file': filename,
                             'action': action, 'measurement': 'render-input centerlines',
                             'max_bone_error_px': round(worst, 8),
                             'status': 'pass' if worst < .01 else 'FAIL'})
                measured.add(filename)
        root = ET.parse(ROOT/'AVA Shimejis'/character/'conf/actions.xml').getroot()
        referenced = {element.get('Image').lstrip('/') for element in root.iter()
                      if element.get('Image')}
        for filename in sorted(referenced-measured):
            rows.append({'character': character, 'file': filename,
                         'action': '', 'measurement': 'raster only; joints not annotated',
                         'max_bone_error_px': '', 'status': 'UNMEASURED'})
        coverage[character] = {
            'reference_video': REFERENCE['video'], 'seconds': REFERENCE['seconds'],
            'master_crop': REFERENCE['characters'][character]['crop'],
            'target_lengths_px': target,
            'measured_unique_frames': len(measured),
            'unmeasured_referenced_rasters': len(referenced-measured),
        }
    out.mkdir(exist_ok=True)
    with (out/'per-frame-check.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (out/'character-targets.json').write_text(json.dumps(coverage, indent=2)+'\n')
    failures = [r for r in rows if r['status'] == 'FAIL']
    print(f"{sum(r['status']=='pass' for r in rows)} procedural frame references checked; {len(failures)} failures")
    for character, data in coverage.items():
        print(character, data['measured_unique_frames'], 'measured;', data['unmeasured_referenced_rasters'], 'raster-only references unmeasured')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
