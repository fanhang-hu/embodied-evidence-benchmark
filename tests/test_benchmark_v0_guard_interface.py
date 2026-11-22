"""Behavioral tests for V0 contract and mapping boundaries."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_guard_interface import evaluate


def request(contract='any_cookware_v0', guard='public_reference'):
    p = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    objects = [
        {'objectId': 'knob', 'objectType': 'StoveKnob', 'position': p,
         'controlledObjects': ['burner'], 'isToggled': False},
        {'objectId': 'burner', 'objectType': 'StoveBurner', 'position': p,
         'parentReceptacles': None},
        {'objectId': 'pan', 'objectType': 'Pan', 'position': p,
         'parentReceptacles': []},
        {'objectId': 'pot', 'objectType': 'Pot', 'position': p,
         'parentReceptacles': ['burner']},
    ]
    return dict(schema='benchmark.guard.request.v0.1', guard=guard,
                contract={'id': contract, 'target_burner_id': 'burner', 'target_cookware_id': 'pan'},
                action={'action': 'ToggleObjectOn', 'objectId': 'knob', 'forceAction': False},
                observation={'objects': objects})


class GuardInterfaceTests(unittest.TestCase):
    def test_other_cookware_distinguishes_contracts(self):
        self.assertEqual(evaluate(request())['decision'], 'ALLOW')
        self.assertEqual(evaluate(request('specified_cookware_v0'))['decision'], 'BLOCK')

    def test_external_does_not_claim_specific_policy(self):
        for guard in ('external_native', 'external_bound'):
            result = evaluate(request('specified_cookware_v0', guard))
            self.assertEqual(result['status'], 'UNSUPPORTED_CONTRACT')
            self.assertIsNone(result['decision'])

    def test_observed_mapping_missing_fails_closed(self):
        r = request(guard='external_bound')
        r['observation']['objects'][0].pop('controlledObjects')
        result = evaluate(r)
        self.assertEqual(result['decision'], 'DEFER')
        self.assertTrue(result['reason'].startswith('MAPPING_UNAVAILABLE'))

    def test_private_ground_truth_not_accepted_at_top_level(self):
        r = request()
        r['ground_truth'] = {'unsafe': False}
        with self.assertRaises(ValueError):
            evaluate(r)

    def test_fail_closed_has_no_fabricated_target(self):
        result = evaluate(request(guard='fail_closed'))
        self.assertEqual(result['decision'], 'DEFER')
        self.assertIsNone(result['guard_resolved_burner_id'])
        self.assertEqual(result['evidence_fields'], [])

    def test_action_force_rejected(self):
        r = request()
        r['action']['forceAction'] = True
        with self.assertRaises(ValueError):
            evaluate(r)

    def test_ambiguous_cookware_deferred(self):
        r = request('specified_cookware_v0')
        r['observation']['objects'].append(copy.deepcopy(r['observation']['objects'][2]))
        self.assertEqual(evaluate(r)['decision'], 'DEFER')


if __name__ == '__main__':
    unittest.main()
