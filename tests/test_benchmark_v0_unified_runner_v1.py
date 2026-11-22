import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_unified_runner_v1 import verify,run,stage_process

PROTOCOL=ROOT/'results/benchmark_v0/unified_execution_protocol_20261122_01/protocol.json'


class UnifiedRunnerTests(unittest.TestCase):
    def test_rejects_changed_case_plan(self):
        plan=verify(PROTOCOL); self.assertEqual(plan['planned_episodes'],48)
        changed=copy.deepcopy(plan); changed['cases'][0]['scene']='FloorPlan999'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'protocol.json'; p.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): verify(p)

    def test_timeout_and_exit_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            timed=stage_process([sys.executable,'-c','import time; time.sleep(30)'],root/'timeout.log',0.1)
            failed=stage_process([sys.executable,'-c','raise SystemExit(7)'],root/'failed.log',5)
            self.assertEqual(timed['status'],'TIMEOUT')
            self.assertEqual((failed['status'],failed['returncode']),('EXITED_NONZERO',7))
            self.assertEqual((root/'timeout.log').stat().st_mode & 0o777,0o600)

    def test_one_failed_backend_does_not_hide_other_or_impute_unified(self):
        def fake_process(command,log,timeout):
            if log.name=='relation_run.log': return dict(status='EXITED_NONZERO',returncode=7,elapsed_ns=1)
            return dict(status='EXITED_ZERO',returncode=0,elapsed_ns=1)
        with tempfile.TemporaryDirectory(dir=ROOT/'results/benchmark_v0') as tmp:
            out=Path(tmp)/'run'
            args=SimpleNamespace(protocol=str(PROTOCOL),out=str(out))
            with patch('benchmark_v0_unified_runner_v1.stage_process',side_effect=fake_process), \
                 patch('benchmark_v0_unified_runner_v1.stage_output_ok',return_value=True):
                self.assertEqual(run(args),1)
            s=json.loads((out/'status.json').read_text()); stages={x['stage']:x['status'] for x in s['stages']}
            self.assertEqual(s['status'],'COMPLETE_WITH_STAGE_FAILURES')
            self.assertEqual(stages['relation_run'],'EXITED_NONZERO')
            self.assertEqual(stages['relation_audit'],'BLOCKED_MISSING_DEPENDENCIES')
            self.assertEqual(stages['attribute_export'],'COMPLETE')
            self.assertEqual(stages['unified_export'],'BLOCKED_MISSING_DEPENDENCIES')
            self.assertFalse((out/'unified_export').exists())

if __name__=='__main__': unittest.main()
