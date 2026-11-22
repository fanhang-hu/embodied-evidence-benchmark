"""Protect archived-plan identity and prevent execution privilege escalation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from e4_validation.plan_replay import ROOT, load_sources, normalize, run_group


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = next(json.loads(l) for l in (ROOT / "configs/exp5/scenario_pilot.jsonl").read_text().splitlines()
                        if json.loads(l)["case_id"] == "attribute_FloorPlan2_01")
        cls.sources = load_sources(ROOT / "results/E4/03_llm_shadow/fp2_live_retry_01/records.jsonl", cls.case)

    def test_three_attack_conditions_share_exact_archived_response(self):
        self.assertEqual(self.sources["C1"], self.sources["C2"])
        self.assertEqual(self.sources["C2"], self.sources["C3"])
        self.assertEqual(self.sources["C1"]["record"]["job_id"], 7)

    def test_normalization_only_adds_unforced_execution_flag(self):
        for source in self.sources.values():
            original = json.loads(source["record"]["raw_response"])["actions"]
            actual = normalize(source["record"]["raw_response"], source["record"]["prompt"]["allowed_actions"])
            self.assertEqual([{k:v for k,v in a.items() if k != "forceAction"} for a in actual], original)
            self.assertTrue(all(a["forceAction"] is False for a in actual))

    def test_invalid_response_cannot_override_executor_flags_or_targets(self):
        allowed = self.sources["C2"]["record"]["prompt"]["allowed_actions"]
        for raw in ['{"actions":[],"actions":[]}', '{"actions":[],"extra":true}',
                    json.dumps(dict(actions=[dict(allowed[-1], forceAction=True)])),
                    json.dumps(dict(actions=[dict(action="PickupObject",objectId="wrong-target")]))]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize(raw, allowed)

    def test_blocked_conditions_never_submit_candidate_to_executor(self):
        # Real frozen rule and routing; fake transport can only accept Pass.
        # Any hidden Pickup call fails this test immediately.
        state_path = (ROOT / "results/E4/02_pairs/pilot_20261022_v2/episodes" /
                      self.case["case_id"] / "unsafe/clean/producer_clean.json")
        state = json.loads(state_path.read_text())
        for group in ("C1", "C3"):
            with self.subTest(group=group), tempfile.TemporaryDirectory(dir=ROOT / "results/E4/04_validation") as temp:
                with patch("e4_validation.plan_replay.prepare", return_value=[]), \
                     patch("e4_validation.plan_replay.approach", return_value=True), \
                     patch("e4_validation.plan_replay.payload", return_value=state), \
                     patch("e4_validation.plan_replay.objects", return_value=state["objects"]), \
                     patch("e4_validation.plan_replay.step", return_value={"request":{"action":"Pass"},"success":True}) as execute:
                    result = run_group(object(), self.case, group, self.sources[group], Path(temp) / group)
                    self.assertFalse(result["steps"][0]["submitted"])
                    self.assertEqual(result["steps"][0]["final_authorization"], "BLOCK")
                    if group == "C1":
                        execute.assert_not_called()
                    else:
                        self.assertEqual(execute.call_count, 1)
                        self.assertEqual(execute.call_args.args[1], {"action":"Pass"})


if __name__ == "__main__":
    unittest.main()
