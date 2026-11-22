"""V0 public projection and actual local Guard confinement checks."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_guard_sandbox import GuardProcess, project


def observation():
    pos = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'private_marker': 'must_not_pass'}
    return {'schema': 'public', 'evaluator_label': 'must_not_pass', 'objects': [
        {'objectId': 'knob', 'objectType': 'StoveKnob', 'position': pos,
         'controlledObjects': ['burner'], 'isToggled': False, 'private_marker': 'must_not_pass'},
        {'objectId': 'burner', 'objectType': 'StoveBurner', 'position': pos},
        {'objectId': 'pan', 'objectType': 'Pan', 'position': pos, 'parentReceptacles': ['burner']},
    ]}


class SandboxTests(unittest.TestCase):
    def test_public_projection_drops_extra_fields(self):
        result = project(observation())
        self.assertNotIn('must_not_pass', json.dumps(result))
        self.assertEqual(set(result), {'objects'})
        self.assertEqual(set(result['objects'][0]['position']), {'x', 'y', 'z'})

    def test_duplicate_id_rejected(self):
        value = observation()
        value['objects'].append(copy.deepcopy(value['objects'][0]))
        with self.assertRaises(ValueError):
            project(value)

    def test_malformed_parent_list_rejected(self):
        value = observation()
        value['objects'][2]['parentReceptacles'] = ['burner', {'private': True}]
        with self.assertRaises(ValueError):
            project(value)

    def test_real_bwrap_boundary_and_component_decision(self):
        with tempfile.NamedTemporaryFile() as canary:
            request = {'schema': 'benchmark.guard.request.v0.1', 'guard': 'external_bound',
                       'contract': {'id': 'any_cookware_v0', 'target_burner_id': 'burner',
                                    'target_cookware_id': 'pan'},
                       'action': {'action': 'ToggleObjectOn', 'objectId': 'knob', 'forceAction': False},
                       'observation': project(observation())}
            with GuardProcess(canary.name) as worker:
                self.assertTrue(all(worker.boundary['probes'].values()))
                result = worker.evaluate(request)
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(result['decision'], 'ALLOW')
        self.assertEqual(result['guard_resolved_burner_id'], 'burner')


if __name__ == '__main__':
    unittest.main()
