import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_candidate_scenes_v1 import candidates


class CandidateSelectionTests(unittest.TestCase):
    def test_deterministic_selection_and_target_binding(self):
        objects = [
            {'objectId': 'pot-b', 'objectType': 'Pot'},
            {'objectId': 'pan-z', 'objectType': 'Pan'},
            {'objectId': 'pan-a', 'objectType': 'Pan'},
            {'objectId': 'burner-b', 'objectType': 'StoveBurner'},
            {'objectId': 'burner-a', 'objectType': 'StoveBurner'},
            {'objectId': 'knob-z', 'objectType': 'StoveKnob', 'isToggled': False, 'controlledObjects': ['burner-b']},
            {'objectId': 'knob-a', 'objectType': 'StoveKnob', 'isToggled': False, 'controlledObjects': ['burner-a']},
            {'objectId': 'knob-0', 'objectType': 'StoveKnob', 'isToggled': True, 'controlledObjects': ['burner-a']},
            {'objectId': 'knob-1', 'objectType': 'StoveKnob', 'isToggled': False, 'controlledObjects': ['burner-a', 'burner-b']},
            {'objectId': 'knob-2', 'objectType': 'StoveKnob', 'isToggled': False, 'controlledObjects': ['missing']},
        ]
        cookware, pairs = candidates(objects)
        self.assertEqual([o['objectId'] for o in cookware], ['pan-a', 'pan-z', 'pot-b'])
        self.assertEqual(pairs, [('knob-a', 'burner-a'), ('knob-z', 'burner-b')])
        self.assertEqual(candidates(list(reversed(objects))), (cookware, pairs))

    def test_no_invented_candidate_when_missing_evidence(self):
        cookware, pairs = candidates([{'objectId': 'pot', 'objectType': 'Pot'},
                                       {'objectId': 'knob', 'objectType': 'StoveKnob', 'isToggled': False}])
        self.assertEqual(len(cookware), 1)
        self.assertEqual(pairs, [])


if __name__ == '__main__': unittest.main()
