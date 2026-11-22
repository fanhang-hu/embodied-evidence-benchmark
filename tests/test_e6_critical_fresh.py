import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from e5_validation.common import file_sha, write_json
from e6_validation.metrics import summarize
from e6_validation.runtime_audit_v4 import audit
from e6_validation.runtime_v4 import authorize
import test_e6_producer as legacy


class CriticalFreshTests(unittest.TestCase):
    run_attribute = legacy.PipelineWithFakeControllerTests.run_attribute

    def row(self, condition):
        with patch("e6_validation.runtime_v3.authorize", side_effect=authorize):
            return self.run_attribute(condition, "critical_only_fresh", runtime_v3=True)

    def test_fresh_after_corrective_write_without_initial_cache(self):
        row = self.row("clean_unsafe")
        self.assertTrue(row["safe_task_success"])
        self.assertEqual(len(row["steps"]), 2)
        self.assertEqual(len(row["trusted_queries"]), 1)
        self.assertEqual(row["steps"][0]["consumed_evidence"]["channel"], "producer_stdout")
        self.assertEqual(row["steps"][1]["consumed_evidence"]["epoch"], 1)
        self.assertGreaterEqual(row["trusted_queries"][0]["request_monotonic_ns"],
                                row["steps"][1]["consumption_ns"])

    def test_unsafe_is_blocked_and_benign_is_executed(self):
        attacked, benign = self.row("producer_attack"), self.row("benign_safe")
        self.assertEqual(attacked["steps"][0]["authorization"], "BLOCK")
        self.assertIsNone(attacked["steps"][0]["executor_receipt"])
        self.assertTrue(benign["safe_task_success"])
        self.assertEqual(len(benign["trusted_queries"]), 1)

    def test_audit_rejects_old_evidence_and_hidden_initial_query(self):
        original = self.row("clean_unsafe")
        original["episode_index"] = 0
        assignment = {k: original[k] for k in
                      ("case_id", "condition", "arm", "pollution_mode", "persistence")}
        protocol = dict(expected=1, assignments=[assignment], cases=[original["case"]],
                        planner_mode="archived_exact_prompt", split="development")
        with tempfile.TemporaryDirectory() as directory, patch(
                "e6_validation.runtime_audit_v4.load_cache", return_value=self.archive_cache):
            run = Path(directory)

            def check(row):
                write_json(run / "result.json", row)
                (run / "records.jsonl").write_text(json.dumps(dict(
                    episode_index=0, episode_file="result.json",
                    sha256=file_sha(run / "result.json"))) + "\n")
                write_json(run / "summary.json", summarize([row], 1))
                return audit(run, protocol)

            self.assertEqual(check(original)["audited"], 1)
            old = copy.deepcopy(original)
            q = old["steps"][-1]["consumed_evidence"]["trusted_query"]
            q["request_monotonic_ns"] = old["steps"][-1]["consumption_ns"] - 1
            old["trusted_queries"] = [q]
            with self.assertRaisesRegex(ValueError, "before consumption"):
                check(old)
            hidden = copy.deepcopy(original)
            hidden["trusted_queries"].insert(0, copy.deepcopy(hidden["trusted_queries"][0]))
            with self.assertRaisesRegex(ValueError, "accounting"):
                check(hidden)
