import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_candidate_evaluation_v1 import aggregate, protocol_check
from benchmark_v0_suite_v1 import ARMS, CONDITIONS


class CandidateEvaluationTests(unittest.TestCase):
    def test_frozen_protocol_rejects_case_substitution(self):
        path = ROOT / 'results/benchmark_v0/candidate_evaluation_protocol_20261122_01/protocol.json'
        protocol = protocol_check(path)
        self.assertEqual(protocol['planned_episodes'], 48)
        modified = copy.deepcopy(protocol); modified['cases'][0]['pan_id'] = 'unregistered'
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'protocol.json'; p.write_text(json.dumps(modified))
            with self.assertRaises(ValueError): protocol_check(p)

    def test_failed_case_is_planned_but_not_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); d = out / 'run_good'; d.mkdir()
            fields = dict(unsafe_candidates=1, unsafe_allowed=1, actual_violations=1,
                          safe_candidates=0, safe_candidate_executed=0, safe_deferred=0, protected_queries=0)
            groups = [dict(condition=c, arm=a, **fields) for c in CONDITIONS for a in ARMS]
            (d / 'summary.json').write_text(json.dumps({'groups': groups}))
            cases = [dict(case_id='good', status='AUDITED'), dict(case_id='bad', status='FAILED')]
            result = aggregate(cases, out)
            self.assertTrue(all(g['planned'] == 2 and g['audited_completed'] == 1 for g in result))
            self.assertTrue(all(g['unsafe_allowed'] == 1 and g['actual_violations'] == 1 for g in result))


if __name__ == '__main__': unittest.main()
