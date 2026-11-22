"""Dangerous plans need public goal attainment, not impossible private safe goals."""
import unittest
from pathlib import Path

from e4_validation.shadow_gate import assess

ROOT=Path(__file__).resolve().parents[1]


class PilotGateTests(unittest.TestCase):
    def test_known_development_dangerous_plan_is_eligible(self):
        result=assess(ROOT/"results/E4/03_llm_shadow/fp2_live_retry_01")
        self.assertEqual(result["eligible_case_ids"],["attribute_FloorPlan2_01"])
        relation=next(c for c in result["cases"] if c["family"]=="relation")
        self.assertFalse(relation["eligible"])

    def test_network_failure_is_not_a_negative_model_result(self):
        result=assess(ROOT/"results/E4/03_llm_shadow/fp34_live_01")
        self.assertFalse(result["eligible_case_ids"])
        self.assertTrue(result["missing_outputs_are_not_negative_model_results"])
        for case in result["cases"]:
            self.assertIn("shared_no_valid_model_output",case["reasons"])


if __name__=="__main__":unittest.main()
