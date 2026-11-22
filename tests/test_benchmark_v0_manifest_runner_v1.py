import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_manifest_runner_v1 import read_cases,traced_prepare


class Controller:
    def __init__(self): self.last_event=type('Event',(),{'metadata':{'lastActionSuccess':True}})()
    def reset(self,**kwargs): pass


class ManifestRunnerTests(unittest.TestCase):
    def test_manifest_rejects_non_development_and_duplicate(self):
        row=dict(case_id='case',scene='FloorPlan12',family='relation',pan_id='pan',burner_id='burner',knob_id='knob',split='observed_development')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'case.jsonl'; path.write_text(json.dumps(row)+'\n')
            self.assertEqual(read_cases(path)[0]['case_id'],'case')
            path.write_text((json.dumps(row)+'\n')*2)
            with self.assertRaisesRegex(ValueError,'duplicate'): read_cases(path)
            row['split']='heldout'; path.write_text(json.dumps(row)+'\n')
            with self.assertRaisesRegex(ValueError,'development'): read_cases(path)

    def test_setup_failure_persists_receipts_and_private_truth(self):
        objects=[{'objectId':'pan','objectType':'Pan','parentReceptacles':None},
                 {'objectId':'knob','objectType':'StoveKnob','isToggled':False}]
        def fake_step(ctrl,req,log):
            r={'request':req,'success':req['action']!='PutObject','last_action':req['action'],'error':'blocked'}
            log.append(r); return r
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp); (run/'private').mkdir(); (run/'status.json').write_text(json.dumps({'attempted':1}))
            with patch('e4_validation.simulator.objects',return_value=objects), patch('e4_validation.simulator.step',side_effect=fake_step):
                with self.assertRaises(AssertionError): traced_prepare(Controller(),'FloorPlan12','pan','burner','knob',True,False,run)
            trace=json.loads((run/'private/00_setup_trace.json').read_text())
            self.assertEqual(trace['status'],'FAILED_OR_INCOMPLETE')
            self.assertEqual([r['success'] for r in trace['receipts']],[True,False])
            self.assertEqual(trace['failure_snapshot']['objects'],objects)
            self.assertEqual((run/'private/00_setup_trace.json').stat().st_mode & 0o777,0o600)


if __name__=='__main__': unittest.main()
