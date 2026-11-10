"""Finite source-video actions, separate from procedural art generation."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tools' / 'video_actions.json'


def manifest():
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'actions': []}


def xml_blocks(char):
    actions, behaviors = [], []
    for a in manifest()['actions']:
        if a['character'] != char:
            continue
        name = a['name']
        lines = [f'\t\t<Action Name="{name}" Type="Animate" BorderType="Floor" Loop="false">', '\t\t\t<Animation>']
        for frame in a['frames']:
            lines.append(f'\t\t\t\t<Pose Image="/{frame}" ImageAnchor="80,144" Velocity="0,0" Duration="1" />')
        lines += ['\t\t\t</Animation>', '\t\t</Action>']
        actions.append('\n'.join(lines))
        cond = escape("#{mascot.environment.workArea.bottom == mascot.anchor.y}", {'"': '&quot;'})
        # Explicit successor is stronger than a host-dependent behavior-name check:
        # every new action must leave for roaming before another can be selected.
        behaviors.append(f'''\t\t<Behavior Name="{name}" Frequency="12" Condition="{cond}">
\t\t\t<NextBehaviorList Add="false">
\t\t\t\t<BehaviorReference Name="WalkAlongWorkAreaFloor" Frequency="3" />
\t\t\t\t<BehaviorReference Name="RunAlongWorkAreaFloor" Frequency="1" />
\t\t\t</NextBehaviorList>
\t\t</Behavior>''')
    return actions, behaviors


def patch(raw, char, kind, eol):
    import re
    start, end = f'<!-- AVA:video:{kind}:start -->', f'<!-- AVA:video:{kind}:end -->'
    raw = re.sub(r'[ \t]*'+re.escape(start)+r'.*?'+re.escape(end)+r'[ \t]*\r?\n', '', raw, flags=re.S)
    blocks = xml_blocks(char)[0 if kind == 'actions' else 1]
    if not blocks:
        return raw
    closing = '</ActionList>' if kind == 'actions' else '</BehaviorList>'
    index = raw.index(closing); index = raw.rfind('\n', 0, index)+1
    block = '\t\t'+start+'\n'+'\n'.join(blocks)+'\n\t\t'+end+'\n'
    return raw[:index]+block.replace('\n', eol)+raw[index:]
