"""C3 native proxy boundary tests without Unity."""
import unittest

from e5_validation.c_temporal.c3_notice_adapter import (
    NoticeProxy,
)
from e5_validation.c_temporal.c3_notice_policy import (
    ARMS, decide,
)
from e4_validation.protocol import critical_action


class Event:
    def __init__(self, request):
        self.metadata = {
            "lastActionSuccess": True,
            "lastAction": request["action"],
            "errorMessage": "",
        }


class FakeController:
    def __init__(self):
        self.actions = []

    def step(self, **request):
        self.actions.append(request)
        return Event(request)

    def reset(self, **kwargs):
        return None


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw = FakeController()
        self.proxy = NoticeProxy(self.raw)

        self.proxy.start_after_capture({
            "receipt": {
                "success": True,
                "last_action": "Pass",
                "request": {"action": "Pass"},
            },
            "capture_monotonic_ns": 1,
        })

    def test_records_native_steps_in_order(self):
        self.proxy.step(
            action="GetReachablePositions"
        )
        self.proxy.step(
            action="ToggleObjectOn",
            objectId="Knob",
            forceAction=False,
        )

        data = self.proxy.seal()

        self.assertEqual(
            len(data["full_history"]), 2
        )
        self.assertEqual(
            [
                x["seq"]
                for x in data["delivered_stream"]
            ],
            [1, 2],
        )
        self.assertTrue(
            data["continuous_from_capture"]
        )
        self.assertTrue(
            data["exclusive_writer_assumed"]
        )

    def test_withheld_real_event_fail_closed(self):
        self.proxy.step(
            action="GetReachablePositions"
        )
        self.proxy.step(
            action="ToggleObjectOn",
            objectId="Knob",
            forceAction=False,
        )

        data = self.proxy.seal(
            withheld_seq=2
        )

        self.assertFalse(
            data["continuous_from_capture"]
        )
        self.assertEqual(
            len(data["delivered_stream"]), 1
        )

        case = {
            "family": "attribute",
            "pan_id": "Pan",
            "burner_id": "Burner",
            "knob_id": "Knob",
        }

        cache = {
            "source_id": "X_protected_native_Pass"
        }

        result = decide(
            cache,
            critical_action(case),
            case,
            data["delivered_stream"],
            mode=ARMS[0],
            capture_verified=True,
            access_granted=True,
            continuous_from_capture=data[
                "continuous_from_capture"
            ],
            settled_through_check=True,
            exclusive_writer=True,
        )

        self.assertEqual(
            result["final"], "DEFER"
        )
        self.assertEqual(
            result["reason"],
            "UNPROVEN_COVERAGE",
        )

    def test_seal_blocks_new_action_until_released(self):
        self.proxy.seal()

        with self.assertRaises(RuntimeError):
            self.proxy.step(
                action="ToggleObjectOn",
                objectId="Knob",
            )

        self.proxy.begin_post_guard()
        self.proxy.step(action="Pass")

        self.assertEqual(
            len(self.proxy.recorded()), 0
        )

    def test_reset_after_capture_fails(self):
        with self.assertRaises(RuntimeError):
            self.proxy.reset(
                scene="FloorPlan5"
            )

    def test_capture_requires_real_success(self):
        with self.assertRaises(ValueError):
            NoticeProxy(
                FakeController()
            ).start_after_capture({
                "receipt": {
                    "success": False,
                    "last_action": "Pass",
                    "request": {
                        "action": "Pass"
                    },
                },
                "capture_monotonic_ns": 1,
            })


if __name__ == "__main__":
    unittest.main()
