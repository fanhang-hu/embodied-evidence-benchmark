"""All providers/controllers below are mocks; no scientific results are emitted."""
import copy
import fcntl
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from e5_validation.common import read_json
from e6_validation.evidence_checks import verify_episode
from e6_validation.online_audit import audit
from e6_validation.online_runtime import checkpoint, commit, failure_row, reconcile, run
from e6_validation.online_session import JournalPlanner, durable_json
import test_e6_producer as legacy


RESPONSE = dict(finish_reason="stop", raw_response='{"actions":[{"action":"PickupObject","objectId":"pan"}]}')


def protocol_fixture():
    case, public = legacy.fixture()
    case.update(case_id="unit", scene="unit")
    assignments = [dict(case_id="unit", condition="benign_safe", arm=arm,
                        pollution_mode="pair", persistence="persistent") for arm in ("shared", "independent_fresh")]
    return dict(expected=2, online_call_budget=2, assignments=assignments, cases=[case],
                split="heldout", planner_mode="online_actual_request", provider_config=dict(
                    base_url="https://example.org", model="unit", timeout=1, max_tokens=80,
                    api_key_env="E6_UNIT_KEY")), case, public


class DurableOnlineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.protocol, self.case, self.public = protocol_fixture()
        self.env = patch.dict("os.environ", {"E6_UNIT_KEY": "unit-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def planner(self):
        return JournalPlanner(self.root / "online_calls", self.protocol, "unit-hash")

    def start(self, index):
        durable_json(self.root / "starts" / f"{index:04d}.json",
                     dict(assignment=self.protocol["assignments"][index]))

    def test_restart_cannot_reset_budget_or_reuse_response(self):
        with patch("e6_validation.online_session.invoke", return_value=RESPONSE) as caller:
            self.planner().provide_for(0, self.public, self.case)
            with self.assertRaisesRegex(ValueError, "already reserved"):
                self.planner().provide_for(0, self.public, self.case)
            self.planner().provide_for(1, self.public, self.case)
            with self.assertRaisesRegex(ValueError, "budget"):
                self.planner().provide_for(2, self.public, self.case)
            self.assertEqual(caller.call_count, 2)
        self.assertEqual(len(self.planner().inventory()), 2)

    def test_interrupted_request_is_accounted_without_retry(self):
        self.start(0)
        with patch("e6_validation.online_session.invoke", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.planner().provide_for(0, self.public, self.case)
        rows = reconcile(self.root, self.protocol, self.planner())
        self.assertEqual(rows[0]["status"], "INTERRUPTED")
        self.assertIsNone(rows[0]["execution_violation"])
        self.assertEqual(rows[0]["reserved_calls"], 1)
        with patch("e6_validation.online_runtime.finish_hashes"):
            summary = checkpoint(self.root, rows, self.protocol, self.planner(), "TEST")
        self.assertEqual(summary["groups"], [])
        self.assertEqual(audit(self.root, self.protocol, "unit-hash")["status"], "PASS_ACCOUNTING_ONLY")
        with self.assertRaisesRegex(ValueError, "already reserved"):
            self.planner().provide_for(0, self.public, self.case)

    def test_error_text_is_not_persisted_and_failed_call_is_consumed(self):
        with patch("e6_validation.online_session.invoke", side_effect=OSError(1, "unit-secret")):
            with self.assertRaises(OSError):
                self.planner().provide_for(0, self.public, self.case)
        terminal = self.planner().inventory()[0]["terminal"]
        self.assertEqual(terminal["error"]["errno"], 1)
        self.assertNotIn("unit-secret", self.planner().result_path(0).read_text())
        self.assertEqual(terminal["status"], "FAILED")

    def test_response_cannot_be_moved_to_another_slot(self):
        with patch("e6_validation.online_session.invoke", return_value=RESPONSE):
            self.planner().provide_for(0, self.public, self.case)
            self.planner().provide_for(1, self.public, self.case)
        terminal = read_json(self.planner().result_path(0))
        durable_json(self.planner().result_path(1), terminal, replace=True)
        with self.assertRaisesRegex(ValueError, "bound to its reservation"):
            self.planner().inventory()

    def test_invalid_response_is_retained_and_consumes_its_slot(self):
        response = dict(finish_reason="stop", raw_response='{"actions":[{"action":"DestroyObject","objectId":"pan"}]}')
        with patch("e6_validation.online_session.invoke", return_value=response):
            with self.assertRaises(ValueError):
                self.planner().provide_for(0, self.public, self.case)
        terminal = self.planner().inventory()[0]["terminal"]
        self.assertEqual(terminal["failure_phase"], "response_validation")
        self.assertEqual(terminal["response"], response)

    def test_changed_committed_result_cannot_be_accepted_on_resume(self):
        self.start(0)
        row = failure_row(self.protocol, 0, "FAILED_OR_INCOMPLETE", reserved_calls=0)
        commit(self.root, row)
        with patch("e6_validation.online_runtime.finish_hashes"):
            checkpoint(self.root, [row], self.protocol, self.planner(), "TEST")
        row["error"] = "changed"
        durable_json(self.root / "episodes/0000.json", row, replace=True)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            reconcile(self.root, self.protocol, self.planner())

    def test_second_runner_cannot_enter_locked_run(self):
        out = self.root / "results/E6/unit"
        out.mkdir(parents=True)
        args = SimpleNamespace(protocol=str(self.root / "protocol.json"), out=str(out), limit=1)
        with (out / ".run.lock").open("a") as lock, patch(
                "e6_validation.online_runtime.ROOT", self.root), patch(
                "e6_validation.online_runtime.check_protocol", return_value=self.protocol), patch(
                "e6_validation.online_runtime.start_controller") as starter:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, "holds this run's lock"):
                run(args)
            starter.assert_not_called()

    def test_runner_stops_on_failure_and_resumes_next_slot(self):
        workspace = self.root / "results/E6"
        workspace.mkdir(parents=True)
        protocol_path = self.root / "protocol.json"
        durable_json(protocol_path, self.protocol)
        args = SimpleNamespace(protocol=str(protocol_path), out=str(workspace / "unit"), limit=2)

        def episode(controller, case, assignment, provider, mode):
            provider(self.public, case)
            raise AssertionError("Mock provider is required to fail")

        with patch("e6_validation.online_runtime.ROOT", self.root), patch(
                "e6_validation.online_runtime.check_protocol", return_value=self.protocol), patch(
                "e6_validation.online_runtime.start_controller") as starter, patch(
                "e6_validation.online_runtime.run_episode", side_effect=episode), patch(
                "e6_validation.online_runtime.finish_hashes"), patch(
                "e6_validation.online_session.invoke", side_effect=OSError(1, "blocked")) as caller:
            run(args)
            out = Path(args.out)
            first_result = (out / "episodes/0000.json").read_bytes()
            self.assertEqual(caller.call_count, 1)
            self.assertEqual(read_json(out / "summary.json")["stop_reason"], "STOP_ON_FAILURE")
            run(args)
            self.assertEqual(caller.call_count, 2)
            self.assertEqual(first_result, (out / "episodes/0000.json").read_bytes())
            summary = read_json(out / "summary.json")
            self.assertEqual((summary["next_index"], summary["reserved_calls"]), (2, 2))
            self.assertEqual(summary["groups"], [])
            self.assertFalse(summary["rates_valid_for_complete_matrix"])
            run(args)
            self.assertEqual(caller.call_count, 2)
            self.assertEqual(starter.call_count, 2)


class TraceCompletenessTests(unittest.TestCase):
    run_attribute = legacy.PipelineWithFakeControllerTests.run_attribute

    def test_complete_online_audit_binds_call_to_episode(self):
        row = self.run_attribute("benign_safe", "shared", runtime_v3=True)
        protocol, case, _ = protocol_fixture()
        protocol.update(expected=1, online_call_budget=1, assignments=protocol["assignments"][:1])
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"E6_UNIT_KEY": "unit"}):
            out = Path(directory)
            planner = JournalPlanner(out / "online_calls", protocol, "unit-hash")
            start = row["planner_publication"]["received_ns"]
            with patch("e6_validation.online_session.invoke", return_value=RESPONSE), patch(
                    "e6_validation.online_session.time.perf_counter_ns", side_effect=[start+1, start+2]):
                row["plan"] = planner.provide_for(0, row["planner_input"], case)
            row.update(episode_index=0, planner_mode="online_actual_request", online_llm_calls=1)
            durable_json(out / "starts/0000.json", dict(assignment=protocol["assignments"][0]))
            commit(out, row)
            with patch("e6_validation.online_runtime.finish_hashes"):
                checkpoint(out, [row], protocol, planner, "TEST")
            self.assertTrue(audit(out, protocol, "unit-hash")["matrix_fully_verified"])
            altered = copy.deepcopy(row)
            altered["plan"]["call_index"] = 1
            durable_json(out / "episodes/0000.json", altered, replace=True)
            with patch("e6_validation.online_runtime.finish_hashes"):
                checkpoint(out, [altered], protocol, planner, "TEST")
            with self.assertRaisesRegex(ValueError, "exact episode"):
                audit(out, protocol, "unit-hash")

    def test_unexplained_truncation_is_rejected(self):
        row = self.run_attribute("clean_unsafe", "independent_fresh", runtime_v3=True)
        verify_episode(row)
        row["steps"] = row["steps"][:-1]
        with self.assertRaisesRegex(ValueError, "truncated"):
            verify_episode(row)

    def test_old_fresh_query_and_detached_submission_log_are_rejected(self):
        original = self.run_attribute("producer_attack", "independent_fresh", runtime_v3=True)
        verify_episode(original)
        row = copy.deepcopy(original)
        row["steps"][0]["consumed_evidence"]["trusted_query"]["request_monotonic_ns"] = 0
        with self.assertRaisesRegex(ValueError, "Fresh evidence"):
            verify_episode(row)
        row = self.run_attribute("benign_safe", "shared", runtime_v3=True)
        row["mutation_receipts"] = []
        with self.assertRaisesRegex(ValueError, "submission log"):
            verify_episode(row)
