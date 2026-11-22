import copy
import unittest

from e4_validation.protocol import critical_action
from e5_validation.task_recovery import ARMS, goal, load_cache, lookup, may_recover, unsafe


class RecoveryPolicyTests(unittest.TestCase):
    def test_native_failure_is_not_a_safety_rejection_trigger(self):
        self.assertFalse(may_recover(ARMS[2], "NATIVE_ACTION_FAILED", False))
        self.assertTrue(may_recover(ARMS[3], "NATIVE_ACTION_FAILED", False))
        self.assertTrue(may_recover(ARMS[2], "BLOCK", False))

    def test_budget_and_no_recovery_control(self):
        self.assertFalse(may_recover(ARMS[1], "BLOCK", False))
        self.assertFalse(may_recover(ARMS[3], "BLOCK", True))
        self.assertTrue(may_recover(ARMS[4], "DEFER", False))

    def test_goal_reached_does_not_erase_unsafe_submission(self):
        case = dict(family="attribute", pan_id="pan", knob_id="knob", burner_id="burner")
        before = dict(objects=[dict(objectId="pan", isPickedUp=False), dict(objectId="knob", isToggled=True)])
        after = copy.deepcopy(before)
        after["objects"][0]["isPickedUp"] = True
        self.assertTrue(unsafe(critical_action(case), before, case))
        self.assertFalse(goal(after, case))
        after["objects"][1]["isToggled"] = False
        self.assertTrue(goal(after, case))

    def test_plan_cache_uses_public_prompt_not_private_initial_label(self):
        from e5_validation.common import CATALOGUE, ROOT, read_jsonl, state
        case = read_jsonl(ROOT / CATALOGUE)[0]
        public = state(copy.deepcopy(case["trials"][0]["S_true"]))
        plan = lookup(public, case, load_cache())
        self.assertEqual(plan["mode"], "archived_real_llm_identical_public_prompt")
        self.assertTrue(all(a["forceAction"] is False for a in plan["actions"]))
        changed = copy.deepcopy(public)
        next(o for o in changed["objects"] if o["objectId"] == case["pan_id"])["isPickedUp"] = True
        with self.assertRaisesRegex(ValueError, "PLAN_CACHE_MISS"):
            lookup(changed, case, load_cache())


if __name__ == "__main__":
    unittest.main()
