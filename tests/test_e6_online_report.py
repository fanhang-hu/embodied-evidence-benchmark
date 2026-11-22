"""Pure reporting/preflight tests; synthetic records are never stored as experiments."""
import unittest
from unittest.mock import patch

from e6_validation.online_report import build, outcome
from e6_validation.online_workflow import preflight
from test_e6_online_session import protocol_fixture
import test_e6_producer as legacy


class OnlineReportingTests(unittest.TestCase):
    run_attribute = legacy.PipelineWithFakeControllerTests.run_attribute

    def test_complete_abstention_has_no_unsafe_denominator(self):
        protocol, _, _ = protocol_fixture()
        protocol.update(expected=1, online_call_budget=1, assignments=protocol["assignments"][:1])
        row = self.run_attribute("benign_safe", "shared", runtime_v3=True)
        row.update(episode_index=0, steps=[], safe_task_success=False, planner_mode="online_actual_request")
        row["plan"].update(actions=[], planner_latency_ns=0)
        calls = {0: dict(terminal=dict(status="OK", response=dict(usage=None)))}
        report, entries = build(protocol, [row], calls, dict(matrix_fully_verified=True))
        self.assertEqual(entries[0]["outcome"], "PLANNER_ABSTAINED")
        metrics = report["full_matrix_metrics"][0]
        self.assertIsNone(metrics["UAR_candidate"]["rate"])
        self.assertIsNone(metrics["execution_ASR_exposed"]["rate"])
        self.assertEqual(metrics["safe_task_success"]["rate"], 0)

    def test_pending_and_partial_matrix_never_produce_rates(self):
        protocol, _, _ = protocol_fixture()
        report, entries = build(protocol, [], {}, dict(matrix_fully_verified=False))
        self.assertEqual(report["status"], "NOT_STARTED")
        self.assertIsNone(report["full_matrix_metrics"])
        self.assertTrue(all(e["execution_violation"] is None for e in entries))
        self.assertEqual(report["pending"], 2)
        row = dict(protocol["assignments"][0], episode_index=0, status="FAILED_OR_INCOMPLETE")
        calls = {0: dict(terminal=dict(status="FAILED", failure_phase="request"))}
        report, entries = build(protocol, [row], calls, dict(matrix_fully_verified=False))
        self.assertEqual(entries[0]["outcome"], "REQUEST_FAILED")
        self.assertIsNone(entries[0]["safe_task_success"])
        self.assertEqual(report["token_usage"]["total_tokens"]["reserved_calls_missing_value"], 1)
        self.assertIsNone(report["full_matrix_metrics"])

    def test_abstention_native_failure_and_guard_denial_are_distinct(self):
        row = dict(status="COMPLETED", plan=dict(actions=[]), execution_violation=False,
                   safe_task_success=False, steps=[])
        self.assertEqual(outcome(row, None), "PLANNER_ABSTAINED")
        row["plan"]["actions"] = [dict(action="PickupObject")]
        row["steps"] = [dict(authorization="BLOCK", executor_receipt=None)]
        self.assertEqual(outcome(row, None), "GUARD_DENIED")
        row["steps"] = [dict(authorization="ALLOW", executor_receipt=dict(success=False))]
        self.assertEqual(outcome(row, None), "NATIVE_ACTION_FAILED")
        interrupted = dict(status="INTERRUPTED")
        self.assertEqual(outcome(interrupted, dict(terminal=dict(status="OK"))), "INTERRUPTED_EXECUTION_UNKNOWN")

    def test_invalid_response_retains_usage_without_claiming_execution(self):
        protocol, _, _ = protocol_fixture()
        row = dict(protocol["assignments"][0], episode_index=0, status="FAILED_OR_INCOMPLETE")
        calls = {0: dict(terminal=dict(status="FAILED", failure_phase="response_validation",
                                      response=dict(usage=dict(total_tokens=42))))}
        report, entries = build(protocol, [row], calls, dict(matrix_fully_verified=False))
        self.assertEqual(entries[0]["outcome"], "RESPONSE_INVALID")
        self.assertEqual(report["token_usage"]["total_tokens"]["known_sum"], 42)
        self.assertEqual(report["token_usage"]["prompt_tokens"]["reserved_calls_missing_value"], 1)
        self.assertIsNone(entries[0]["execution_violation"])

    def test_preflight_blocks_before_requests_and_does_not_confuse_socket_with_api(self):
        protocol, _, _ = protocol_fixture()
        with patch("e6_validation.online_workflow.load_bashrc"), patch(
                "e6_validation.online_workflow.provider_config", return_value=protocol["provider_config"]), patch(
                "e6_validation.online_workflow.socket.socket", side_effect=PermissionError(1, "blocked")):
            result = preflight(protocol)
        self.assertEqual(result["status"], "LOCAL_SOCKET_UNAVAILABLE")
        self.assertEqual(result["requests_made"], 0)
        with patch("e6_validation.online_workflow.load_bashrc"), patch(
                "e6_validation.online_workflow.provider_config", return_value=protocol["provider_config"]), patch(
                "e6_validation.online_workflow.socket.socket"):
            result = preflight(protocol)
        self.assertFalse(result["API_connectivity_verified"])


if __name__ == "__main__":
    unittest.main()
