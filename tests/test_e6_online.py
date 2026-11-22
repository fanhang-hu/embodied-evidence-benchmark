import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from e6_validation.online_planner import OnlinePlanner, parse_actions


class OnlineBoundaryTests(unittest.TestCase):
    def test_rejects_force_unknown_target_duplicate_keys_and_truncation(self):
        prompt = dict(allowed_actions=[dict(action="PickupObject", objectId="pan")])
        for raw in ('{"actions":[{"action":"PickupObject","objectId":"pan","forceAction":true}]}',
                    '{"actions":[{"action":"PickupObject","objectId":"other"}]}',
                    '{"actions":[],"actions":[]}'):
            with self.assertRaises(ValueError):
                parse_actions(dict(finish_reason="stop", raw_response=raw), prompt)
        with self.assertRaises(ValueError):
            parse_actions(dict(finish_reason="length", raw_response='{"actions":[]}'), prompt)

    def test_live_planning_budget_and_no_archive_fallback(self):
        case = dict(family="attribute", pan_id="pan", knob_id="knob", burner_id="burner")
        public = dict(objects=[dict(objectId="pan", objectType="Pan", parentReceptacles=[], isPickedUp=False),
                               dict(objectId="knob", objectType="StoveKnob", isToggled=False),
                               dict(objectId="burner", objectType="StoveBurner")])
        response = dict(finish_reason="stop", raw_response='{"actions":[{"action":"PickupObject","objectId":"pan"}]}')
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                "os.environ", {"DEEPSEEK_API_KEY": "unit-secret", "DEEPSEEK_BASE_URL": "https://example.org",
                               "E4_LLM_BASE_URL": ""}), patch(
                "e6_validation.online_planner.invoke", return_value=response) as caller:
            planner = OnlinePlanner(Path(directory), max_calls=1)
            result = planner.provide(public, case)
            self.assertEqual(result["mode"], "online_actual_request")
            self.assertFalse(result["actions"][0]["forceAction"])
            self.assertNotIn("unit-secret", (Path(directory)/"call_000.json").read_text())
            with self.assertRaisesRegex(RuntimeError, "budget"):
                planner.provide(public, case)
            self.assertEqual(caller.call_count, 1)


if __name__ == "__main__":
    unittest.main()
