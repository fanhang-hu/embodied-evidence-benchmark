"""Read-only E5-C C2/C3 gap audit; no Unity/LLM actions."""

import json
from collections import Counter
from pathlib import Path

from e4_validation.protocol import obj
from e5_validation.common import (
    ROOT, file_sha, new_output, read_json, read_jsonl,
    write_json, finish_hashes,
)
from e5_validation.a_consistent_pollution.runner import selected_cases

BASE = Path("results/E5/C_temporal_validity")
C1_RUN = BASE / "07_native/c1_formal_20261024_01"
C1_REPORT = BASE / "08_report/c1_formal_audit_20261024_01"
C1_FREEZE = BASE / "05_protocol/c1_formal_freeze_20261024_01/manifest.json"

STALE = Path("results/E5/staleness/native_trace_20261023_01")
BIND = Path("results/E5/binding/native_20261023_02")

OUTPUT = BASE / "09_gap_audit/c2_c3_source_audit_20261024_01"


def ensure(condition, message):
    if not condition:
        raise AssertionError(message)


def j(path):
    path = ROOT / path
    ensure(path.is_file(), f"MISSING: {path}")
    return read_json(path)


def jl(path):
    path = ROOT / path
    ensure(path.is_file(), f"MISSING: {path}")
    return read_jsonl(path)


def main():
    files = [
        C1_RUN / "records.jsonl",
        C1_RUN / "summary.json",
        C1_REPORT / "summary.json",
        C1_FREEZE,
        STALE / "records.jsonl",
        STALE / "summary.json",
        BIND / "records.jsonl",
        BIND / "summary.json",
    ]

    for f in files:
        ensure((ROOT / f).is_file(), f"MISSING: {f}")

    records = jl(C1_RUN / "records.jsonl")
    report = j(C1_REPORT / "summary.json")
    formal_summary = j(C1_RUN / "summary.json")
    frozen = j(C1_FREEZE)

    ensure(
        len(records) == 15 and formal_summary["complete"] is True,
        "C1 not complete",
    )
    ensure(
        report["status"] == "PASS" and report["audited"] == 15,
        "C1 audit incomplete",
    )
    ensure(
        report["records_sha256"]
        == file_sha(ROOT / C1_RUN / "records.jsonl"),
        "C1 audit source hash changed",
    )

    for name, expected in frozen["source_sha256"].items():
        ensure(
            (ROOT / name).is_file()
            and file_sha(ROOT / name) == expected,
            f"C1 frozen source changed: {name}",
        )

    cases = {c["case_id"]: c for c in selected_cases()}
    ensure(len(cases) == 5, "Expected 5 C1 attribute cases")

    count = Counter()
    transitions = []
    visible = []
    plans = {}

    print("===== C3: NATIVE CHANGE RECEIPT VISIBILITY =====")

    for r in records:
        case = cases[r["case_id"]]
        arm = r["arm"]
        folder = ROOT / r["evidence_dir"]

        captured = read_json(
            folder / "S_off_capture_original.json"
        )
        monitor_input = read_json(
            folder / "S_monitor_used.json"
        )
        truth = read_json(
            folder / "S_true_submission_private.json"
        )
        plan = read_json(
            folder / "llm_plan.json"
        )

        ident = (
            plan["request_sha256"],
            json.dumps(plan["actions"], sort_keys=True),
        )

        if r["case_id"] in plans:
            ensure(
                plans[r["case_id"]] == ident,
                "C1 paired plan differs",
            )

        plans[r["case_id"]] = ident

        ensure(
            obj(captured, case["knob_id"])["isToggled"] is False,
            "Capture not OFF",
        )
        ensure(
            r["online_model_calls"] == 0,
            "Unexpected online planner",
        )

        count[arm] += 1

        row = {
            "case_id": r["case_id"],
            "arm": arm,
            "original_version": captured.get("state_version"),
            "monitor_version": monitor_input.get("state_version"),
            "monitor_source_id": monitor_input.get("source_id"),
            "receipt_recorded_by_evaluator": False,
            "receipt_supplied_to_guard": False,
            "original_snapshot_used": monitor_input == captured,
            "fresh_native_query_count": r["query_count"],
        }

        if arm != "C1_0_static":
            change = read_json(
                folder / "native_change_receipt.json"
            )
            after_change = read_json(
                folder / "S_after_change_private.json"
            )

            ensure(
                change["success"] is True,
                "Native change not successful",
            )
            ensure(
                change["request"] == {
                    "action": "ToggleObjectOn",
                    "objectId": case["knob_id"],
                    "forceAction": False,
                },
                "Unexpected native change action",
            )
            ensure(
                obj(
                    after_change, case["knob_id"]
                )["isToggled"] is True,
                "Actual transition missing",
            )
            ensure(
                obj(
                    truth, case["knob_id"]
                )["isToggled"] is True,
                "Submission state not ON",
            )
            ensure(
                r["plan_ready_monotonic_ns"]
                < r["native_change_complete_monotonic_ns"]
                < r["check_monotonic_ns"],
                "Native transition outside plan/check interval",
            )

            row["receipt_recorded_by_evaluator"] = True
            row["transition_receipt_path"] = str(
                Path(r["evidence_dir"])
                / "native_change_receipt.json"
            )
            transitions.append(row["transition_receipt_path"])

            if arm == "C1_1_stale":
                ensure(
                    monitor_input == captured
                    and r["query_count"] == 0,
                    "Stale did not use old evidence",
                )
                ensure(
                    r["final_authorization"] == "ALLOW"
                    and r["execution_violation"] is True,
                    "Stale mechanism result differs",
                )

            elif arm == "C1_2_fresh":
                fresh = read_json(
                    folder / "S_fresh_monitor.json"
                )
                query = read_json(
                    folder / "fresh_pass_receipt.json"
                )

                ensure(
                    monitor_input == fresh
                    and query["receipt"]["success"] is True,
                    "Fresh evidence missing",
                )
                ensure(
                    r["query_count"] == 1,
                    "Unexpected fresh query budget",
                )
                ensure(
                    r["final_authorization"] == "BLOCK"
                    and r["execution_violation"] is False,
                    "Fresh mechanism result differs",
                )
            else:
                raise AssertionError(f"Unexpected arm: {arm}")

        else:
            ensure(
                monitor_input == captured
                and r["query_count"] == 0
                and r["safe_task_success"] is True,
                "Static control differs",
            )

        visible.append(row)

    for arm in (
        "C1_0_static",
        "C1_1_stale",
        "C1_2_fresh",
    ):
        ensure(count[arm] == 5, f"Wrong count for {arm}")

    ensure(
        len(transitions) == 10,
        "Expected 10 successful native change receipts",
    )

    print("C1 groups:", dict(count))
    print("Recorded OFF-to-ON receipts:", len(transitions))
    print(
        "Receipt directly supplied to Monitor: NO "
        "(C1 Monitor uses S_monitor_used snapshots)"
    )

    print("\n===== C2: EXISTING TARGET-BINDING COVERAGE =====")

    stale_summary = j(STALE / "summary.json")
    stale_rows = jl(STALE / "records.jsonl")

    ensure(
        stale_summary["actual_recorded_transitions"] == 8
        and len(stale_rows) == 40,
        "Historical stale count mismatch",
    )
    ensure(
        stale_summary["candidate_actions_submitted"] == 0,
        "Historical stale candidate unexpectedly submitted",
    )

    changed_rows = [
        r for r in stale_rows
        if r["condition"] == "T1_stale_cache_at_new_truth"
    ]
    ensure(
        len(changed_rows) == 8,
        "Expected 8 old transition probes",
    )

    binding_summary = j(BIND / "summary.json")
    binding_rows = jl(BIND / "records.jsonl")

    ensure(
        binding_summary["physical_controls"] == 9
        and len(binding_rows) == 54,
        "Binding count mismatch",
    )
    ensure(
        binding_summary["candidate_actions_submitted"] == 0,
        "Binding candidate unexpectedly executed",
    )

    arrangements = {
        (r["case_id"], r["placement"], r["evidence_dir"])
        for r in binding_rows
    }

    ensure(
        len(arrangements) == 9,
        "Physical placement count differs",
    )
    ensure(
        len(set(r["method"] for r in binding_rows)) == 6,
        "Expected six binding methods",
    )

    print("Physical binding controls:", len(arrangements))
    print("Binding judgments:", len(binding_rows))
    print(
        "Historical relation state-change probes:",
        sum(r["family"] == "relation" for r in changed_rows),
    )
    print("Stale relation candidate executions:", 0)

    summary = {
        "status": "PASS",
        "classification": (
            "Read-only retrospective gap audit on E5 development data"
        ),
        "c1_formal_episodes": 15,
        "c1_group_counts": dict(count),
        "native_off_to_on_receipts_saved": len(transitions),
        "receipt_visible_to_guard_in_c1": False,
        "visibility_reason": (
            "C1 passes S_monitor_used to the Monitor. "
            "native_change_receipt is retained by the Evaluator, "
            "not passed as authorization evidence."
        ),
        "deployment_read_permission_verified": False,
        "receipt_authentication_verified": False,
        "full_single_writer_history_guaranteed_in_deployment": False,
        "version_evidence": (
            "state_version is an application-level index supplied "
            "to protected_query, not a native authenticated "
            "state-change counter"
        ),
        "c2_existing_static_controls": len(arrangements),
        "c2_existing_binding_decisions": len(binding_rows),
        "c2_actual_target_transition_probes": sum(
            r["family"] == "relation" for r in changed_rows
        ),
        "c2_target_transition_candidates_executed_from_stale_decisions": 0,
        "c3_native_change_notices_observable_by_guard": "NOT_ESTABLISHED",
        "c3_automatic_cache_invalidation_demonstrated": False,
        "c3_unconditional_fresh_query_prevents_observed_c1_violation": True,
        "possible_followup": (
            "Test ordered, access-controlled transition "
            "notifications only if a defensible Guard input path "
            "can be established. Otherwise report a conditional "
            "upper bound or stop."
        ),
        "source_sha256": {
            str(f): file_sha(ROOT / f)
            for f in files
        },
    }

    out = new_output(OUTPUT)

    write_json(out / "summary.json", summary)
    write_json(out / "c1_visibility_matrix.json", visible)
    write_json(
        out / "binding_controls.json",
        [
            {
                "case_id": a,
                "placement": b,
                "evidence_dir": c,
            }
            for a, b, c in sorted(arrangements)
        ],
    )

    finish_hashes(out)

    print("\n===== E5-C C2/C3 EVIDENCE GAP =====")

    for key in (
        "c1_formal_episodes",
        "native_off_to_on_receipts_saved",
        "receipt_visible_to_guard_in_c1",
        "deployment_read_permission_verified",
        "c2_existing_static_controls",
        "c2_existing_binding_decisions",
        "c2_actual_target_transition_probes",
        "c2_target_transition_candidates_executed_from_stale_decisions",
        "c3_automatic_cache_invalidation_demonstrated",
    ):
        print(key, ":", summary[key])

    print("Output:", out)
    print("E5-C C2/C3 GAP AUDIT: PASS")


if __name__ == "__main__":
    main()
