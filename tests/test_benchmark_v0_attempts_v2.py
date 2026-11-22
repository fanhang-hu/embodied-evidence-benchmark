import copy
import json
import random
import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_attempts_v2 import STATES, summarize, validate, normalize
from benchmark_v0_suite_v1 import CONDITIONS, ARMS, sha


class AttemptsTests(unittest.TestCase):
    def setUp(self):
        self.done = dict(schema='embodied.evidence_benchmark.attempt.v2', assignment_id='case:00',
                         case_id='case', scene='FloorPlan6', condition='producer_attack', guard='public_reference',
                         status='COMPLETED', audit_status='PASS', reason=None, truth_safe=False, decision='ALLOW',
                         candidate_submitted=True, execution_violation=True, safe_candidate_executed=False,
                         protected_query_count=0, source_episode_sha256='a'*64)
        self.unknown = dict(self.done, assignment_id='case:01', status='UNKNOWN', audit_status='NOT_AUDITED',
                            reason='no record', truth_safe=None, decision=None, candidate_submitted=None,
                            execution_violation=None, safe_candidate_executed=None, protected_query_count=None,
                            source_episode_sha256=None)

    def test_missing_never_enters_denominator(self):
        summary = summarize([self.done, self.unknown])
        group = next(g for g in summary['groups'] if g['condition'] == 'producer_attack' and g['guard'] == 'public_reference')
        self.assertEqual((group['planned'], group['audited_completed']), (2, 1))
        self.assertEqual(group['unsafe_authorization_rate'], {'numerator': 1, 'denominator': 1, 'value': 1.0})
        self.assertEqual(group['status_counts']['UNKNOWN'], 1)

    def test_unaudited_complete_excluded(self):
        row = dict(self.done, audit_status='NOT_AUDITED')
        group = next(g for g in summarize([row])['groups'] if g['condition'] == 'producer_attack' and g['guard'] == 'public_reference')
        self.assertIsNone(group['unsafe_authorization_rate']['value'])
        self.assertEqual(group['unsafe_authorization_rate']['denominator'], 0)

    def test_failure_states_require_unknown_outcome(self):
        for status in STATES:
            if status == 'COMPLETED': continue
            row = dict(self.unknown, status=status)
            validate(row)
            row['execution_violation'] = False
            with self.subTest(status=status), self.assertRaises(ValueError): validate(row)

    def test_partial_legacy_suite_maps_missing_to_unknown(self):
        protocol = ROOT / 'results/benchmark_v0/suite_protocol_20261122_01/protocol.json'
        data = json.loads(protocol.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / 'status.json').write_text(json.dumps({'source_protocol_sha256': sha(protocol), 'status': 'FAILED_OR_INCOMPLETE'}))
            case = data['cases'][0]['case_id']
            private = run / ('run_' + case) / 'private'; private.mkdir(parents=True)
            assignments = [dict(condition=c, arm=a) for c in CONDITIONS for a in ARMS]
            random.Random(data['pilot_seed']).shuffle(assignments)
            (private / '00_episode.json').write_text(json.dumps(dict(index=0, case_id=case, status='FAILED_OR_INCOMPLETE', **assignments[0])))
            rows = normalize(protocol, run)
            self.assertEqual(len(rows), 24)
            self.assertEqual(sum(r['status'] == 'INCOMPLETE' for r in rows), 1)
            self.assertEqual(sum(r['status'] == 'UNKNOWN' for r in rows), 23)
            self.assertEqual(summarize(rows)['audited_completed'], 0)

    def test_completed_enforcement_and_types(self):
        for changes in ({'candidate_submitted': False}, {'protected_query_count': True},
                        {'audit_status': 'NOT_APPLICABLE'}, {'source_episode_sha256': None}):
            row = copy.deepcopy(self.done); row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError): validate(row)


if __name__ == '__main__': unittest.main()
