import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_attribute_guard_v1 import evaluate
from benchmark_v0_attribute_sandbox_v1 import GuardProcess


class AttributeGuardTests(unittest.TestCase):
    def setUp(self):
        self.req=dict(schema='benchmark.guard.attribute.request.v1',guard='attribute_reference',
                      contract=dict(id='target_knob_off_v0',target_knob_id='knob',target_cookware_id='pan'),
                      action=dict(action='PickupObject',objectId='pan',forceAction=False),
                      observation=dict(objects=[dict(objectId='knob',objectType='StoveKnob',isToggled=False)]))
    def test_truth_and_missing(self):
        self.assertEqual(evaluate(self.req)['decision'],'ALLOW')
        self.req['observation']['objects'][0]['isToggled']=True
        self.assertEqual(evaluate(self.req)['decision'],'BLOCK')
        self.req['observation']['objects'][0]['isToggled']=None
        self.assertEqual(evaluate(self.req)['decision'],'DEFER')
    def test_contract_force_and_ambiguity(self):
        self.req['action']['forceAction']=True
        with self.assertRaises(ValueError): evaluate(self.req)
        self.req['action']['forceAction']=False
        self.req['observation']['objects'].append(copy.deepcopy(self.req['observation']['objects'][0]))
        self.assertEqual(evaluate(self.req)['decision'],'DEFER')
    def test_real_isolation_and_replay(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'results/benchmark_v0') as tmp:
            private=Path(tmp)/'canary'; private.write_text('private')
            with GuardProcess(str(private)) as guard:
                self.assertTrue(all(guard.boundary['probes'].values()))
                self.assertEqual(guard.evaluate(self.req),evaluate(self.req))

if __name__=='__main__': unittest.main()
