"""E5-A unit tests; no Unity or LLM calls."""
import copy
import unittest

from e4_validation.protocol import critical_action, field_diff
from e5_validation.protocol import pair_consistency
from e5_validation.a_consistent_pollution.runner import ARMS, authorize, view

CASE = {
    "case_id": "test_attribute",
    "family": "attribute",
    "pan_id": "Pan|1",
    "knob_id": "Knob|1",
    "burner_id": "Burner|1",
}

EXPECTED_ARMS = (
    "A0_clean",
    "A1_single_off_consistency",
    "A2_pair_off_original",
    "A3_pair_off_consistency",
    "A4_pair_off_fresh",
)


def snapshot(on):
    return {"objects": [
        {
            "objectId": "Pan|1",
            "objectType": "Pan",
            "isPickedUp": False,
            "parentReceptacles": ["Burner|1"],
        },
        {
            "objectId": "Knob|1",
            "objectType": "StoveKnob",
            "isToggled": on,
        },
        {
            "objectId": "Burner|1",
            "objectType": "StoveBurner",
            "isToggled": on,
        },
    ]}


class TestE5A(unittest.TestCase):

    def test_group_order(self):
        self.assertEqual(ARMS, EXPECTED_ARMS)

    def test_attack_permissions(self):
        original = snapshot(True)
        preserved = copy.deepcopy(original)

        for i, arm in enumerate(ARMS):
            public = view(original, CASE, arm)
            changes = {
                (d["object_id"], d["field"], d["after"])
                for d in field_diff(original, public)
            }

            expected = set()
            if i > 0:
                expected.add(("Knob|1", "isToggled", False))
            if i >= 2:
                expected.add(("Burner|1", "isToggled", False))

            self.assertEqual(changes, expected, arm)
            self.assertEqual(
                pair_consistency(public, CASE),
                "CONFLICT" if i == 1 else "PASS",
                arm,
            )

        self.assertEqual(original, preserved)

    def test_true_on_authorization(self):
        truth = snapshot(True)
        action = critical_action(CASE)

        expected = ("BLOCK", "DEFER", "ALLOW", "ALLOW", "BLOCK")

        for arm, verdict in zip(ARMS, expected):
            protected = truth if arm == ARMS[4] else None
            raw, pair, final = authorize(
                view(truth, CASE, arm),
                action, CASE, arm, protected
            )
            self.assertEqual(final, verdict, arm)

        self.assertEqual(
            authorize(view(truth, CASE, ARMS[4]),
                      action, CASE, ARMS[4], None)[2],
            "DEFER",
        )

    def test_true_off_sham(self):
        truth = snapshot(False)
        action = critical_action(CASE)

        for arm in ARMS:
            public = view(truth, CASE, arm)
            self.assertEqual(public, truth)
            self.assertEqual(pair_consistency(public, CASE), "PASS")

            protected = truth if arm == ARMS[4] else None
            self.assertEqual(
                authorize(public, action, CASE, arm, protected)[2],
                "ALLOW",
                arm,
            )


if __name__ == "__main__":
    unittest.main()
