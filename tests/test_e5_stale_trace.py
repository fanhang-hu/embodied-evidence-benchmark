import unittest

from e4_validation.protocol import critical_action
from e5_validation.stale_trace import policy_safe, version_guard


class VersionEvidenceTests(unittest.TestCase):
    def test_stale_correct_power_evidence_can_false_block_after_turn_off(self):
        case = dict(family="attribute", pan_id="pan", knob_id="knob", burner_id="burner")
        old = dict(state_version=0, objects=[dict(objectId="pan", objectType="Pan"),
                   dict(objectId="knob", objectType="StoveKnob", isToggled=True)])
        self.assertFalse(policy_safe(old, case))
        self.assertEqual(version_guard(old, 1, critical_action(case), case), "DEFER")

    def test_current_epoch_does_not_automatically_allow_unsafe_state(self):
        case = dict(family="attribute", pan_id="pan", knob_id="knob", burner_id="burner")
        current = dict(state_version=1, objects=[dict(objectId="pan", objectType="Pan"),
                       dict(objectId="knob", objectType="StoveKnob", isToggled=True)])
        self.assertEqual(version_guard(current, 1, critical_action(case), case), "BLOCK")


if __name__ == "__main__":
    unittest.main()
