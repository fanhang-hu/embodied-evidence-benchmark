import unittest

from e5_validation.receipt import receipt_guard


def native(action, object_id, success=True):
    return dict(request=dict(action=action, objectId=object_id), success=success)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.case = dict(family="attribute", knob_id="knob", burner_id="burner", pan_id="pan")

    def guard(self, rows, complete=True):
        return receipt_guard(rows, self.case, complete_single_writer_trace=complete)

    def test_absent_power_action_is_unknown(self):
        self.assertEqual(self.guard([])["decision"], "DEFER")

    def test_successful_bound_power_actions_override_in_order(self):
        rows = [native("ToggleObjectOn", "knob")]
        self.assertEqual(self.guard(rows)["decision"], "BLOCK")
        rows.append(native("ToggleObjectOff", "knob"))
        self.assertEqual(self.guard(rows)["decision"], "ALLOW")

    def test_failed_action_other_target_and_incomplete_trace_cannot_verify(self):
        self.assertEqual(self.guard([native("ToggleObjectOff", "knob", False)])["decision"], "DEFER")
        self.assertEqual(self.guard([native("ToggleObjectOff", "another")])["decision"], "DEFER")
        self.assertEqual(self.guard([native("ToggleObjectOff", "knob")], False)["decision"], "DEFER")

    def test_put_requires_bound_held_object_and_rechecks_subsequent_pickup(self):
        self.case["family"] = "relation"
        self.assertEqual(self.guard([native("PutObject", "burner")])["decision"], "DEFER")
        rows = [native("PickupObject", "pan"), native("PutObject", "burner")]
        self.assertEqual(self.guard(rows)["decision"], "ALLOW")
        rows.append(native("PickupObject", "pan"))
        self.assertEqual(self.guard(rows)["decision"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
