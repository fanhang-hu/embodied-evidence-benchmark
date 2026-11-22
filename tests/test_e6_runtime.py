import json
import tempfile
import unittest
from pathlib import Path

from e5_validation.common import file_sha, write_json
from e6_validation.metrics import summarize
from e6_validation.runtime_audit import audit
from e6_validation.runtime_v3 import load_rows
import test_e6_producer as legacy


class RuntimeVisibilityTests(unittest.TestCase):
    run_attribute = legacy.PipelineWithFakeControllerTests.run_attribute
    def test_negative_visibility_does_not_skip_unforced_native_execution(self):
        row = self.run_attribute("producer_attack", "shared", runtime_v3=True, visible=False)
        self.assertFalse(row["steps"][0]["navigation"]["success"])
        self.assertEqual(row["steps"][0]["authorization"], "ALLOW")
        self.assertTrue(row["steps"][0]["executor_receipt"]["success"])
        self.assertTrue(row["execution_violation"])

    def test_negative_visibility_does_not_bypass_protected_guard(self):
        row = self.run_attribute("producer_attack", "independent_fresh", runtime_v3=True, visible=False)
        self.assertFalse(row["steps"][0]["navigation"]["success"])
        self.assertEqual(row["steps"][0]["authorization"], "BLOCK")
        self.assertIsNone(row["steps"][0]["executor_receipt"])

    def test_checkpoint_hash_and_full_matrix_audit(self):
        row = self.run_attribute("producer_attack", "independent_fresh", runtime_v3=True)
        row["episode_index"] = 0
        assignment = {k: row[k] for k in ("case_id", "condition", "arm", "pollution_mode", "persistence")}
        protocol = dict(expected=1, assignments=[assignment], cases=[row["case"]],
                        planner_mode="archived_exact_prompt", split="development")
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory, patch(
                "e6_validation.runtime_audit.load_cache", return_value=self.archive_cache):
            run = Path(directory)
            write_json(run/"result.json", row)
            (run/"records.jsonl").write_text(json.dumps(dict(episode_index=0, episode_file="result.json",
                                                           sha256=file_sha(run/"result.json")))+"\n")
            write_json(run/"summary.json", summarize([row], 1))
            self.assertEqual(len(load_rows(run)), 1)
            self.assertEqual(audit(run, protocol)["audited"], 1)
            row["steps"][0]["authorization"] = "ALLOW"
            write_json(run/"result.json", row)
            with self.assertRaisesRegex(ValueError, "hash"):
                load_rows(run)
