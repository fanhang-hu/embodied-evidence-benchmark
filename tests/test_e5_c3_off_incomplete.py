"""Meaningful evidence-selection and benign incompleteness checks, no Unity."""
import copy
import unittest

from e4_validation.protocol import critical_action
from e5_validation.c_temporal.c3_off_incomplete import select_withheld
from e5_validation.c_temporal.c3_notice_policy import ARMS, decide, finish_fresh


class BenignIncompleteTests(unittest.TestCase):
    def test_selects_first_actual_navigation_not_state_change_or_failed_action(self):
        events = [dict(seq=i+1, receipt=dict(success=ok, request=dict(action=action)))
                  for i, (action, ok) in enumerate([
                      ("ToggleObjectOn", True), ("TeleportFull", False),
                      ("GetReachablePositions", True), ("TeleportFull", True)])]
        saved = copy.deepcopy(events)
        self.assertEqual(select_withheld(events), 3)
        self.assertEqual(events, saved)

    def test_no_eligible_notice_never_manufactures_one(self):
        self.assertIsNone(select_withheld([]))
        self.assertIsNone(select_withheld([dict(seq=1, receipt=dict(success=True,
            request=dict(action="ToggleObjectOff")))]))

    def test_actual_safe_cache_does_not_override_known_missing_coverage(self):
        case = dict(family="attribute", pan_id="pan", knob_id="knob", burner_id="burner")
        cache = dict(source_id="X_protected_native_Pass", objects=[
            dict(objectId="pan", objectType="Pan"),
            dict(objectId="knob", objectType="StoveKnob", isToggled=False)])
        for arm in ARMS:
            decision = decide(cache, critical_action(case), case, [], mode=arm,
                capture_verified=True, access_granted=True, continuous_from_capture=False,
                settled_through_check=True, exclusive_writer=True)
            self.assertEqual(decision["reason"], "UNPROVEN_COVERAGE")
            self.assertEqual(decision["final"], "DEFER" if arm == ARMS[0] else "PENDING_FRESH")
            self.assertEqual(decision["needs_query"], arm == ARMS[1])
            if arm == ARMS[1]:
                bad_receipt = dict(receipt=dict(success=False, last_action="Pass", request=dict(action="Pass")))
                self.assertEqual(finish_fresh(decision, cache, bad_receipt, critical_action(case), case), "DEFER")


if __name__ == "__main__":
    unittest.main()
