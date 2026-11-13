"""Regressions for the supplied Green/Bonk stall and native repeat log."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import ava_common as spec
import validate
NS={'m':'http://www.group-finity.com/Mascot'}


class AutonomousRecoveryTests(unittest.TestCase):
    def test_bonk_has_finite_idle_recovery(self):
        for char in spec.CHARS:
            tree=E.parse(ROOT/'AVA Shimejis'/char/'conf/actions.xml')
            bonk=tree.find('.//m:Action[@Name="Bonk"]',NS)
            self.assertEqual([r.get('Name') for r in bonk],['Hurt','Idle'])
            for name in ('Hurt','Idle'):
                action=tree.find(f'.//m:Action[@Name="{name}"]',NS)
                self.assertEqual(action.get('Type'),'Animate')
                self.assertNotEqual(action.get('Loop'),'true')

    def test_validator_catches_reported_stall(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf=Path(tmp)/'AVA Shimejis/Green/conf'
            shutil.copytree(ROOT/'AVA Shimejis/Green/conf',conf)
            path=conf/'actions.xml';raw=path.read_text()
            start=raw.index('<Action Name="Bonk"');end=raw.index('</Action>',start)
            block=raw[start:end].replace('Name="Idle"','Name="Stand"')
            path.write_text(raw[:start]+block+raw[end:])
            failures=[]
            with patch.object(validate,'ROOT',tmp):validate.check_xml('Green',failures)
            self.assertTrue(any('unbounded Stay reference Stand' in x for x in failures),failures)

    @unittest.skipUnless(shutil.which('node'),'Node needed to execute native JavaScript condition')
    def test_repeat_guard_with_both_real_host_formats(self):
        expr=spec.repeat_condition('Wave')
        script='const expr='+json.dumps(expr)+''';
for(const [name,expected] of [['Behavior(Wave)',false],['Behavior[name=Wave]',false],['Behavior[name=Cheer]',true]]) {
 const mascot={getBehavior:()=>({toString:()=>name})};
 if(eval(expr)!==expected) throw Error(name);
}
'''
        subprocess.run(['node','-e',script],check=True)

    def test_edge_waits_have_native_repeat_guard(self):
        for char in spec.CHARS:
            tree=E.parse(ROOT/'AVA Shimejis'/char/'conf/behaviors.xml')
            for name in ('HoldOntoWall','HoldOntoCeiling'):
                condition=tree.find(f'.//m:Behavior[@Name="{name}"]',NS).get('Condition')
                self.assertIn('Behavior[name='+name+']',condition)


if __name__=='__main__':unittest.main()
