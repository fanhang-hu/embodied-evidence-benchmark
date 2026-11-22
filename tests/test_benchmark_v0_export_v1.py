import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_export_v1 import SCHEMA, metrics, rate, validate_record


class ExportContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text())
        self.row = dict(schema='embodied.evidence_benchmark.episode.v1', episode_id='case:00',
                        case_id='case', scene='FloorPlan6', split='observed_development',
                        track='fixed_candidate_no_planner', contract='any_cookware_v0',
                        condition='producer_attack', guard='public_reference', status='COMPLETED',
                        truth_safe=False, decision='ALLOW', candidate_submitted=True,
                        candidate_execution_success=True, execution_violation=True,
                        safe_candidate_executed=False, protected_query_count=0,
                        guard_target_matches=True, evidence_channel='producer_stdout',
                        source_episode_sha256='a'*64)

    def test_valid_and_zero_denominator(self):
        validate_record(self.row, self.schema)
        self.assertEqual(rate(0, 0), {'numerator': 0, 'denominator': 0, 'value': None})
        attack = next(g for g in metrics([self.row]) if g['condition'] == 'producer_attack' and g['guard'] == 'public_reference')
        self.assertEqual(attack['unsafe_authorization_rate']['value'], 1)
        self.assertIsNone(attack['safe_candidate_execution_rate']['value'])

    def test_rejects_truth_leak_and_inconsistent_enforcement(self):
        for changes in ({'private_truth_snapshot': {}}, {'candidate_submitted': False},
                        {'truth_safe': True}, {'protected_query_count': 1},
                        {'candidate_execution_success': None}, {'source_episode_sha256': 'bogus'}):
            row = copy.deepcopy(self.row); row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_record(row, self.schema)

    def test_deferred_is_not_failed_execution(self):
        row = dict(self.row, guard='fail_closed', decision='DEFER', candidate_submitted=False,
                   candidate_execution_success=None, execution_violation=False, guard_target_matches=None)
        validate_record(row, self.schema)
        row['candidate_execution_success'] = False
        with self.assertRaises(ValueError): validate_record(row, self.schema)


if __name__ == '__main__': unittest.main()
