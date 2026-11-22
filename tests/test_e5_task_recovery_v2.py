import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from e4_validation.llm_shadow import build_prompt, sha
from e5_validation.common import ROOT, state
from e5_validation.task_recovery_v2 import run_episode


class NativeFeasibilityTests(unittest.TestCase):
    def exercise(self, native_success):
        items = [dict(objectId="pan", objectType="Pan", isPickedUp=False, parentReceptacles=["burner"]),
                 dict(objectId="knob", objectType="StoveKnob", isToggled=False),
                 dict(objectId="burner", objectType="StoveBurner", isToggled=False)]
        case = dict(case_id="unit", family="attribute", scene="unit_scene", pan_id="pan", knob_id="knob", burner_id="burner",
                    trials=[dict(expected_safe=True, S_true=items), dict(expected_safe=False, S_true=items)])
        prompt = build_prompt(state(items), case)
        cache = {sha(prompt):dict(prompt=prompt, raw_actions=[dict(action="PickupObject", objectId="pan")],
                  request_sha256="unit_request", response_path="unit_response")}
        def execute(controller, request, log):
            if native_success:
                items[0]["isPickedUp"] = True
            return dict(request=request, success=native_success, error="" if native_success else "native precondition failure")
        query = dict(receipt=dict(request=dict(action="Pass"), success=True), query_ns=1,
                     response_monotonic_ns=1)
        with tempfile.TemporaryDirectory(dir=ROOT / "results/E5") as directory, \
             patch("e5_validation.task_recovery_v2.prepare", return_value=[]), \
             patch("e5_validation.task_recovery_v2.objects", side_effect=lambda _:copy.deepcopy(items)), \
             patch("e5_validation.task_recovery_v2.approach", return_value=False), \
             patch("e5_validation.task_recovery_v2.protected_query", side_effect=lambda *_:(state(copy.deepcopy(items)),query)), \
             patch("e5_validation.task_recovery_v2.step", side_effect=execute) as executor:
            row = run_episode(object(), case, True, "G0_clean", Path(directory) / "episode", cache)
            self.assertEqual(executor.call_count, 1)
        return row

    def test_negative_visibility_flag_does_not_replace_policy_authorization(self):
        row = self.exercise(True)
        self.assertFalse(row["steps"][0]["navigation_success"])
        self.assertEqual(row["steps"][0]["final_authorization"], "ALLOW")
        self.assertTrue(row["safe_task_success"])

    def test_native_failure_is_recorded_as_failure_and_never_forced(self):
        row = self.exercise(False)
        self.assertFalse(row["safe_task_success"])
        self.assertEqual(row["stop_reason"], "NATIVE_ACTION_FAILED")
        self.assertIs(row["steps"][0]["candidate"]["forceAction"], False)


if __name__ == "__main__":
    unittest.main()
