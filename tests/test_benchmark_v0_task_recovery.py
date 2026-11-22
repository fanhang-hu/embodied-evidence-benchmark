import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_task_recovery import protocol,recovery_plan


class RecoveryTests(unittest.TestCase):
    def test_held_cookware_is_not_picked_up_a_second_time(self):
        case=dict(family='relation',pan_id='pan',burner_id='burner',knob_id='knob')
        obs=dict(objects=[dict(objectId='pan',isPickedUp=True)])
        actions=[dict(action='PickupObject',objectId='pan',forceAction=False),
                 dict(action='PutObject',objectId='burner',forceAction=False),
                 dict(action='ToggleObjectOn',objectId='knob',forceAction=False)]
        with patch('benchmark_v0_task_recovery.symbolic_provider',return_value=dict(actions=actions,raw_actions=[])):
            result=recovery_plan(obs,case)
        self.assertEqual([a['action'] for a in result['actions']],['PutObject','ToggleObjectOn'])

    def test_assignment_matrix_has_each_comparison_once(self):
        p=protocol()
        self.assertEqual(p['expected'],72)
        self.assertEqual(len({(a['case_id'],a['condition'],a['arm']) for a in p['assignments']}),72)


if __name__=='__main__': unittest.main()
