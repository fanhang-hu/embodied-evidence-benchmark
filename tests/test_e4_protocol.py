"""Security boundary checks on frozen real observations, with no simulator startup."""
import copy
import json
import unittest
from pathlib import Path

from e4_validation.protocol import canonical, critical_action, field_diff, monitor, plan, poison

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "results/E4/01_feasibility/run_20261022_headless_v3/scenario_catalogue.jsonl"


class ProtocolBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = [json.loads(line) for line in CATALOGUE.read_text().splitlines()]
        cls.cases = [r for r in cls.cases if r["status"] == "VALID"]

    def test_attack_isolated_from_native_observation_and_single_field(self):
        for case in self.cases:
            original = {"objects": case["trials"][1]["S_true"]}
            untouched = copy.deepcopy(original)
            corrupted = poison(original, case)
            self.assertEqual(original, untouched)
            difference = field_diff(original, corrupted)
            self.assertEqual(len(difference), 1)
            self.assertEqual(difference[0]["field"], "parentReceptacles" if case["family"] == "relation" else "isToggled")

    def test_missing_evidence_cannot_authorize(self):
        for case in self.cases:
            state = {"objects": copy.deepcopy(case["trials"][0]["S_true"])}
            target_id = case["pan_id"] if case["family"] == "relation" else case["knob_id"]
            target = next(o for o in state["objects"] if o["objectId"] == target_id)
            target.pop("parentReceptacles" if case["family"] == "relation" else "isToggled")
            self.assertEqual(monitor(canonical(state), critical_action(case), case), "DEFER")

    def test_duplicate_identity_and_wrong_target_cannot_authorize(self):
        for case in self.cases:
            state = {"objects": copy.deepcopy(case["trials"][0]["S_true"])}
            candidate = critical_action(case)
            target = next(o for o in state["objects"] if o["objectId"] == candidate["objectId"])
            state["objects"].append(copy.deepcopy(target))
            self.assertEqual(monitor(canonical(state), candidate, case), "DEFER")
            state["objects"].pop()
            candidate["objectId"] = "OtherPhysicalTarget"
            self.assertEqual(monitor(canonical(state), candidate, case), "DEFER")

    def test_forced_actions_cannot_pass_gate(self):
        for case in self.cases:
            state = {"objects": case["trials"][0]["S_true"]}
            candidate = critical_action(case)
            candidate["forceAction"] = True
            self.assertEqual(monitor(canonical(state), candidate, case), "DEFER")

    def test_real_negative_observation_requires_corrective_plan(self):
        for case in self.cases:
            state = {"objects": case["trials"][1]["S_true"]}
            clean = plan(canonical(state), case)
            corrupted = plan(canonical(poison(state, case)), case)
            self.assertGreater(len(clean["actions"]), 1)
            self.assertEqual(corrupted["actions"], [critical_action(case)])
            self.assertEqual(monitor(canonical(state), critical_action(case), case), "BLOCK")


if __name__ == "__main__":
    unittest.main()
