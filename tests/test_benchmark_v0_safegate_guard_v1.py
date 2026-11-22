import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'results/E3/04_contract/safegate/deps'))
from benchmark_v0_safegate_guard_v1 import evaluate
from benchmark_v0_safegate_sandbox_v1 import GuardProcess


class SafeGateAdaptationTests(unittest.TestCase):
    def setUp(self):
        self.req=dict(schema='benchmark.guard.request.v0.1',guard='safegate_z3',
                      contract=dict(id='any_cookware_v0',target_burner_id='b',target_cookware_id='p'),
                      action=dict(action='ToggleObjectOn',objectId='k',forceAction=False),
                      observation=dict(objects=[dict(objectId='k',objectType='StoveKnob',controlledObjects=['b']),
                          dict(objectId='b',objectType='StoveBurner',position=dict(x=0,y=0,z=0)),
                          dict(objectId='p',objectType='Pan',parentReceptacles=['b'],position=dict(x=0,y=0,z=0))]))
    def test_z3_occupancy_geometry_and_missing_binding(self):
        self.assertEqual(evaluate(self.req)['decision'],'ALLOW')
        self.req['observation']['objects'][2]['position']['x']=1
        self.assertEqual(evaluate(self.req)['decision'],'BLOCK')
        self.req['observation']['objects'][0]['controlledObjects']=None
        self.assertEqual(evaluate(self.req)['decision'],'DEFER')
    def test_unforced_action_required(self):
        self.req['action']['forceAction']=True
        with self.assertRaises(ValueError): evaluate(self.req)
    def test_isolated_z3_replay(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'results/benchmark_v0') as tmp:
            path=Path(tmp)/'canary'; path.write_text('private')
            with GuardProcess(str(path)) as guard:
                self.assertTrue(all(guard.boundary['probes'].values()))
                self.assertEqual(guard.evaluate(self.req),evaluate(copy.deepcopy(self.req)))

if __name__=='__main__': unittest.main()
