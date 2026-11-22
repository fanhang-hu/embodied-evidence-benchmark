import unittest

from e4_validation.protocol import critical_action, request
from e5_validation.b_evidence_sources.policy import (
    ARMS, decide, finish_query
)

CASE = dict(
    family="attribute",
    pan_id="Pan|1",
    knob_id="Knob|1",
    burner_id="Burner|1",
)


def state(on):
    return dict(objects=[
        dict(
            objectId="Pan|1",
            objectType="Pan",
            isPickedUp=False,
            parentReceptacles=["Burner|1"],
        ),
        dict(
            objectId="Knob|1",
            objectType="StoveKnob",
            isToggled=on,
        ),
        dict(
            objectId="Burner|1",
            objectType="StoveBurner",
            isToggled=on,
        ),
    ])


def receipt(action, target="Knob|1", success=True):
    return dict(
        request=dict(action=action, objectId=target),
        success=success,
        last_action=action,
    )


class TestReceiptPolicy(unittest.TestCase):

    def check(
        self, *, arm, receipts, candidate=None,
        granted=True, continuous=True
    ):
        return decide(
            state(False),
            candidate or critical_action(CASE),
            CASE,
            receipts,
            arm=arm,
            setup_log_granted=granted,
            trace_continuous=continuous,
        )

    def test_complete_on_blocks_without_query(self):
        for arm in ARMS:
            result = self.check(
                arm=arm,
                receipts=[receipt("ToggleObjectOn")],
            )
            self.assertEqual(result["final"], "BLOCK")
            self.assertFalse(result["needs_query"])

    def test_missing_off_stays_unknown(self):
        result = self.check(arm=ARMS[0], receipts=[])
        self.assertEqual(result["final"], "DEFER")

        pending = self.check(arm=ARMS[1], receipts=[])
        self.assertTrue(pending["needs_query"])

        self.assertEqual(
            finish_query(
                pending, state(False),
                critical_action(CASE), CASE
            ),
            "ALLOW",
        )

        self.assertEqual(
            finish_query(
                pending, state(True),
                critical_action(CASE), CASE
            ),
            "BLOCK",
        )

    def test_wrong_target_or_failed_on(self):
        cases = [
            [receipt("ToggleObjectOn", "WrongKnob")],
            [receipt("ToggleObjectOn", success=False)],
        ]
        for log in cases:
            result = self.check(arm=ARMS[0], receipts=log)
            self.assertEqual(result["final"], "DEFER")

    def test_permission_and_continuity(self):
        log = [receipt("ToggleObjectOn")]

        for options in (
            dict(granted=False),
            dict(continuous=False),
        ):
            result = self.check(
                arm=ARMS[0], receipts=log, **options
            )
            self.assertEqual(result["final"], "DEFER")

    def test_latest_successful_toggle(self):
        log = [
            receipt("ToggleObjectOn"),
            receipt("ToggleObjectOff"),
        ]
        result = self.check(arm=ARMS[0], receipts=log)
        self.assertEqual(result["final"], "ALLOW")

    def test_corrective_toggle_off(self):
        candidate = request("ToggleObjectOff", "Knob|1")
        for arm in ARMS:
            result = self.check(
                arm=arm,
                receipts=[receipt("ToggleObjectOn")],
                candidate=candidate,
            )
            self.assertEqual(result["final"], "ALLOW")
            self.assertFalse(result["needs_query"])

    def test_query_not_allowed_when_unnecessary(self):
        result = self.check(
            arm=ARMS[1],
            receipts=[receipt("ToggleObjectOn")],
        )
        with self.assertRaises(ValueError):
            finish_query(
                result, state(True),
                critical_action(CASE), CASE
            )

    def test_force_action_rejected(self):
        candidate = dict(
            critical_action(CASE), forceAction=True
        )
        result = self.check(
            arm=ARMS[1], receipts=[], candidate=candidate
        )
        self.assertEqual(result["final"], "DEFER")


if __name__ == "__main__":
    unittest.main()
