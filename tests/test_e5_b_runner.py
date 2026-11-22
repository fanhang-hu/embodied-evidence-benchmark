"""E5-B Runner integration boundary tests; no Unity."""

import unittest

from e4_validation.protocol import critical_action
from e5_validation.b_evidence_sources.policy import (
    decide, finish_query,
)
from e5_validation.b_evidence_sources.runner import ARMS


CASE = {
    "family": "attribute",
    "pan_id": "Pan",
    "knob_id": "Knob",
    "burner_id": "Burner",
}


def observation(on):
    return {
        "objects": [
            {
                "objectId": "Pan",
                "objectType": "Pan",
                "isPickedUp": False,
                "parentReceptacles": ["Burner"],
            },
            {
                "objectId": "Knob",
                "objectType": "StoveKnob",
                "isToggled": on,
            },
            {
                "objectId": "Burner",
                "objectType": "StoveBurner",
                "isToggled": on,
            },
        ]
    }


def receipt(action):
    return {
        "request": {
            "action": action,
            "objectId": "Knob",
        },
        "success": True,
        "last_action": action,
    }


class TestE5BRunner(unittest.TestCase):

    def test_arm_names(self):
        self.assertEqual(
            ARMS,
            (
                "B2_receipt_only",
                "B3_receipt_then_fresh",
            ),
        )

    def test_successful_on_receipt_blocks(self):
        action = critical_action(CASE)

        for arm in ARMS:
            result = decide(
                observation(False),
                action,
                CASE,
                [receipt("ToggleObjectOn")],
                arm=arm,
                setup_log_granted=True,
                trace_continuous=True,
            )

            self.assertEqual(result["final"], "BLOCK")
            self.assertFalse(result["needs_query"])

    def test_unknown_requires_fresh_only_in_b3(self):
        action = critical_action(CASE)

        b2 = decide(
            observation(False),
            action,
            CASE,
            [],
            arm=ARMS[0],
            setup_log_granted=True,
            trace_continuous=True,
        )

        b3 = decide(
            observation(False),
            action,
            CASE,
            [],
            arm=ARMS[1],
            setup_log_granted=True,
            trace_continuous=True,
        )

        self.assertEqual(b2["final"], "DEFER")
        self.assertFalse(b2["needs_query"])

        self.assertEqual(b3["final"], "PENDING_FRESH")
        self.assertTrue(b3["needs_query"])

        self.assertEqual(
            finish_query(
                b3,
                observation(False),
                action,
                CASE,
            ),
            "ALLOW",
        )

    def test_no_setup_access_no_receipt_evidence(self):
        action = critical_action(CASE)
        log = [receipt("ToggleObjectOn")]

        for arm in ARMS:
            result = decide(
                observation(False),
                action,
                CASE,
                log,
                arm=arm,
                setup_log_granted=False,
                trace_continuous=True,
            )

            self.assertFalse(result["sufficient"])


if __name__ == "__main__":
    unittest.main()
