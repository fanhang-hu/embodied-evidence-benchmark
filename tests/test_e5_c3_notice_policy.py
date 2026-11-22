"""E5-C C3 notification policy tests; no Unity."""
import copy
import unittest

from e4_validation.protocol import critical_action
from e5_validation.c_temporal.c3_notice_policy import (
    ARMS, decide, finish_fresh,
)

CASE = {
    "family": "attribute",
    "pan_id": "Pan",
    "burner_id": "Burner",
    "knob_id": "Knob",
}

ACTION = critical_action(CASE)

FLAGS = {
    "capture_verified": True,
    "access_granted": True,
    "continuous_from_capture": True,
    "settled_through_check": True,
    "exclusive_writer": True,
}


def snapshot(on=False):
    return {
        "source_id": "X_protected_native_Pass",
        "objects": [
            {
                "objectId": "Pan",
                "objectType": "Pan",
                "isPickedUp": False,
                "parentReceptacles": ["Burner"],
            },
            {
                "objectId": "Burner",
                "objectType": "StoveBurner",
                "isToggled": on,
            },
            {
                "objectId": "Knob",
                "objectType": "StoveKnob",
                "isToggled": on,
            },
        ],
    }


def notice(
    action="ToggleObjectOn",
    target="Knob",
    success=True,
    seq=1,
):
    return {
        "seq": seq,
        "receipt": {
            "request": {
                "action": action,
                "objectId": target,
                "forceAction": False,
            },
            "success": success,
            "last_action": action,
        },
    }


def decide_for(mode, events, **overrides):
    flags = dict(FLAGS)
    flags.update(overrides)

    return decide(
        snapshot(), ACTION, CASE, events,
        mode=mode, **flags,
    )


class NoticePolicyTests(unittest.TestCase):

    def test_complete_unchanged_allows(self):
        for arm in ARMS:
            result = decide_for(arm, [])
            self.assertEqual(
                result["final"], "ALLOW"
            )
            self.assertFalse(result["needs_query"])

    def test_successful_on_invalidates_without_query(self):
        result = decide_for(
            ARMS[0], [notice()]
        )
        self.assertEqual(
            result["final"], "DEFER"
        )
        self.assertFalse(result["needs_query"])
        self.assertEqual(
            result["reason"], "BOUND_STATE_CHANGED"
        )

    def test_successful_on_triggers_fresh(self):
        result = decide_for(
            ARMS[1], [notice()]
        )

        self.assertEqual(
            result["final"], "PENDING_FRESH"
        )
        self.assertTrue(result["needs_query"])

        query = {
            "receipt": {
                "request": {"action": "Pass"},
                "last_action": "Pass",
                "success": True,
            }
        }

        self.assertEqual(
            finish_fresh(
                result, snapshot(True),
                query, ACTION, CASE,
            ),
            "BLOCK",
        )
        self.assertEqual(
            finish_fresh(
                result, snapshot(False),
                query, ACTION, CASE,
            ),
            "ALLOW",
        )

    def test_no_grant_or_unsettled_not_silent_allow(self):
        for flag in (
            "access_granted",
            "continuous_from_capture",
            "settled_through_check",
            "exclusive_writer",
            "capture_verified",
        ):
            for arm, expected in (
                (ARMS[0], "DEFER"),
                (ARMS[1], "PENDING_FRESH"),
            ):
                result = decide_for(
                    arm, [], **{flag: False}
                )
                self.assertEqual(
                    result["final"], expected
                )

    def test_failed_or_wrong_target_do_not_invalidate(self):
        for event in (
            notice(success=False),
            notice(target="OtherKnob"),
        ):
            result = decide_for(
                ARMS[0], [event]
            )
            self.assertEqual(
                result["final"], "ALLOW"
            )

    def test_bad_sequence_and_unknown_action_fail_closed(self):
        for event in (
            notice(seq=2),
            notice(action="Reset"),
        ):
            self.assertEqual(
                decide_for(
                    ARMS[0], [event]
                )["final"],
                "DEFER",
            )
            self.assertEqual(
                decide_for(
                    ARMS[1], [event]
                )["final"],
                "PENDING_FRESH",
            )

    def test_off_after_on_does_not_restore_cache(self):
        events = [
            notice(),
            notice(
                "ToggleObjectOff", seq=2
            ),
        ]
        result = decide_for(
            ARMS[0], events
        )
        self.assertEqual(
            result["final"], "DEFER"
        )

    def test_invalid_query_does_not_allow(self):
        pending = decide_for(
            ARMS[1], [notice()]
        )

        bad_query = {
            "receipt": {
                "request": {"action": "Pass"},
                "success": False,
                "last_action": "Pass",
            }
        }

        self.assertEqual(
            finish_fresh(
                pending, snapshot(False),
                bad_query, ACTION, CASE,
            ),
            "DEFER",
        )

        bad_state = copy.deepcopy(
            snapshot(False)
        )
        bad_state["source_id"] = "T0_E5_adapter"

        good_query = {
            "receipt": {
                "request": {"action": "Pass"},
                "success": True,
                "last_action": "Pass",
            }
        }

        self.assertEqual(
            finish_fresh(
                pending, bad_state,
                good_query, ACTION, CASE,
            ),
            "DEFER",
        )

    def test_unverified_cache_source_fail_closed(self):
        bad = snapshot()
        bad["source_id"] = "T0_E5_adapter"

        result = decide(
            bad, ACTION, CASE, [],
            mode=ARMS[0],
            **FLAGS,
        )
        self.assertEqual(
            result["final"], "DEFER"
        )


if __name__ == "__main__":
    unittest.main()
