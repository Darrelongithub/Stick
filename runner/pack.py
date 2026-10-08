"""Read the AvA Shimejis image sets.

The *frames* come from the pack itself (``conf/actions.xml``), so the runner
always reflects whatever art is in the repo - no second copy of the data to
drift.  Only the scheduling logic (which action when) lives in the runner, and
that borrows its weights from ``tools/ava_common.py``.

XML shapes we understand (both come straight out of the pack):

    <Action Name="Walk" Type="Move" BorderType="Floor">
      <Animation>
        <Pose Image="/walk01.png" ImageAnchor="64,128" Velocity="-4,0" Duration="2" />
        ...
      </Animation>
    </Action>

``Sequence``/``Select``/``Embedded`` actions are containers or app-internal
actions - the runner does not need them.  A pose without ``Velocity`` keeps the
velocity of the previous pose, a pose without ``Duration`` lasts 10 ticks, like
Shimeji-ee.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

DEFAULT_DURATION = 10

RUNNER_ACTIONS = {
    # action -> how the runner uses it
    "Stand": "stand",
    "Walk": "walk",
    "Run": "run",
    "Falling": "fall",
    "GrabWall": "wall",
    "ClimbWall": "wall",
    "GrabCeiling": "ceiling",
    "ClimbCeiling": "ceiling",
    "Sprawl": "lie",
    "Tripping": "lie",
    "Hurt": "hurt",
}


class Pose:
    __slots__ = ("image", "anchor", "velocity", "duration")

    def __init__(self, image, anchor, velocity, duration):
        self.image = image
        self.anchor = anchor
        self.velocity = velocity
        self.duration = duration

    def __repr__(self):                                     # pragma: no cover
        return f"Pose({self.image!r}, anchor={self.anchor}, v={self.velocity})"


class Action:
    def __init__(self, name, kind, border, poses):
        self.name = name
        self.kind = kind
        self.border = border
        self.poses = poses

    @property
    def images(self):
        return [p.image for p in self.poses]

    def __repr__(self):                                     # pragma: no cover
        return f"Action({self.name!r}, {self.kind}, {len(self.poses)} poses)"


def _ints(text, count=2, default=(0, 0)):
    if not text:
        return tuple(default)
    parts = [p for p in text.replace(" ", "").split(",") if p != ""]
    try:
        values = [int(float(p)) for p in parts]
    except ValueError:
        return tuple(default)
    while len(values) < count:
        values.append(default[len(values)])
    return tuple(values[:count])


def _parse_pose(node, last_velocity):
    image = (node.get("Image") or "").lstrip("/")
    anchor = _ints(node.get("ImageAnchor"), 2, (64, 128))
    velocity = _ints(node.get("Velocity"), 2, last_velocity)
    duration = node.get("Duration")
    try:
        duration = int(duration) if duration is not None else DEFAULT_DURATION
    except ValueError:
        duration = DEFAULT_DURATION
    return Pose(image, anchor, velocity, max(1, duration))


def parse_actions(path):
    """Every action in a pack's actions.xml as {name: Action}."""
    root = ET.parse(path).getroot()
    actions = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "Action":
            continue
        name = node.get("Name")
        if not name:
            continue
        kind = node.get("Type") or "Animate"
        border = node.get("BorderType")
        poses = []
        velocity = (0, 0)
        for anim in node:
            if anim.tag.rsplit("}", 1)[-1] != "Animation":
                continue
            for pose in anim:
                if pose.tag.rsplit("}", 1)[-1] != "Pose":
                    continue
                parsed = _parse_pose(pose, velocity)
                velocity = parsed.velocity
                poses.append(parsed)
        if poses or kind in ("Sequence", "Select", "Embedded"):
            actions[name] = Action(name, kind, border, poses)
    return actions


class Character:
    """One image set: its actions, its art directory and its scheduling weights."""

    def __init__(self, name, directory, actions):
        self.name = name
        self.directory = directory
        self.actions = actions

    def locate(self, image):
        return os.path.join(self.directory, image)

    def has(self, *names):
        return all(n in self.actions and self.actions[n].poses for n in names)

    def __repr__(self):                                     # pragma: no cover
        return f"Character({self.name!r}, {len(self.actions)} actions)"


def load_character(base, name):
    directory = os.path.join(base, name)
    actions_path = os.path.join(directory, "conf", "actions.xml")
    if not os.path.isfile(actions_path):
        raise FileNotFoundError(f"{name}: {actions_path} is missing")
    return Character(name, directory, parse_actions(actions_path))
