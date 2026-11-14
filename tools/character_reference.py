"""One fixed, timestamped master pose per character; no shared median body.

Lengths follow manually annotated centerlines, not pose bounding-box height.
Each selected crop comes from output.mp4 at 10s. These are approximate 2D
style targets, not a claim of recovered 3D anatomy or subpixel measurement.
"""
import json
import math
from pathlib import Path

REFERENCE = json.loads(Path(__file__).with_name('reference_proportions.json').read_text())


def profile(character):
    points = REFERENCE['characters'][character]
    radius = 18.0 if character == 'Orange' else 12.0
    scale = radius / points['radius']
    distance = lambda a, b: math.dist(points[a], points[b]) * scale
    center_to_shoulder = distance('head', 'shoulder')
    return {
        'neck': radius,
        'neck-shoulder': center_to_shoulder-radius,
        'torso': distance('shoulder', 'hip'),
        'upper arm': distance('shoulder', 'elbow'),
        'forearm': distance('elbow', 'hand'),
        'thigh': distance('hip', 'knee'),
        'shin': distance('knee', 'foot'),
    }


PROFILES = {character: profile(character) for character in REFERENCE['characters']}
