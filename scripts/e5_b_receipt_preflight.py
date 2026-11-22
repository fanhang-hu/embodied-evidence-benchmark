"""E5-B Step 1: read-only receipt provenance and coverage audit."""

from collections import Counter

from e4_validation.protocol import obj
from e5_validation.a_consistent_pollution.runner import selected_cases
from e5_validation.receipt import receipt_guard
from e5_validation.common import (
    ROOT, append_jsonl, file_sha, finish_hashes,
    new_output, read_json, require, write_json
)

SOURCE = ROOT / (
    "results/E5/A_consistent_pollution/"
    "02_native/run_20261024_01"
)

OUT = "results/E5/B_evidence_sources/00_preflight/source_audit_20261024_01"


def main():
    cases = selected_cases()
    require(len(cases) == 5, "Expected exactly five attribute cases")

    out = new_output(OUT)
    rows = []

    for case in cases:
        for safe in (False, True):
            label = "true_off" if safe else "true_on"

            folder = (
                SOURCE / "episodes" / case["case_id"]
                / label / "A2_pair_off_original"
            )

            receipt_path = folder / "setup_receipts.json"
            state_path = folder / "S_true_initial_private.json"

            require(receipt_path.is_file(), f"Missing {receipt_path}")
            require(state_path.is_file(), f"Missing {state_path}")

            receipts = read_json(receipt_path)
            truth = read_json(state_path)

            actual_on = obj(
                truth, case["knob_id"]
            )["isToggled"]

            require(
                actual_on is (not safe),
                f"Initial state mismatch: {case['case_id']} {label}"
            )

            target_events = []

            for index, receipt in enumerate(receipts):
                request = receipt.get("request", {})
                action = request.get("action")

                # Only the exact bound knob is relevant.
                if (
                    request.get("objectId") == case["knob_id"]
                    and action in ("ToggleObjectOn", "ToggleObjectOff")
                ):
                    target_events.append({
                        "index": index,
                        "action": action,
                        "success": receipt.get("success"),
                        "last_action": receipt.get("last_action"),
                    })

            # Conditional upper bound:
            # Guard is assumed to receive a complete,
            # ordered, single-writer setup history.
            complete = receipt_guard(
                receipts,
                case,
                complete_single_writer_trace=True
            )

            # Without a justified continuity guarantee,
            # stored receipts must not be trusted as complete.
            unsealed = receipt_guard(
                receipts,
                case,
                complete_single_writer_trace=False
            )

            # Agent starts with no accessible setup history.
            runtime_only = receipt_guard(
                [],
                case,
                complete_single_writer_trace=False
            )

            row = {
                "case_id": case["case_id"],
                "scene": case["scene"],
                "true_initial": "OFF" if safe else "ON",
                "setup_receipt_count": len(receipts),
                "target_toggle_events": target_events,
                "conditional_complete_decision": complete["decision"],
                "conditional_sufficient": complete["sufficient"],
                "supporting_indices": complete.get(
                    "supporting_receipt_indices", []
                ),
                "unsealed_decision": unsealed["decision"],
                "runtime_only_decision": runtime_only["decision"],
                "receipt_sha256": file_sha(receipt_path),
                "state_sha256": file_sha(state_path),
                "receipt_source": "Evaluator_setup_Unity_action_receipts",
                "physical_root": "same_Unity_instance",
                "guard_read_permission": "ASSUMED_ONLY_NOT_DEPLOYMENT_VERIFIED",
                "trace_continuity": "CONDITIONAL_SINGLE_WRITER_ASSUMPTION",
                "native_sensor_timestamp": None,
                "online_model_calls": 0,
                "unity_calls": 0,
            }

            append_jsonl(out / "records.jsonl", row)
            rows.append(row)

            print(
                f"{case['case_id']} {label}: "
                f"toggles={target_events}, "
                f"complete={complete['decision']}, "
                f"sufficient={complete['sufficient']}, "
                f"unsealed={unsealed['decision']}, "
                f"runtime_only={runtime_only['decision']}",
                flush=True
            )

    require(len(rows) == 10, "Expected 10 initial states")

    on = [r for r in rows if r["true_initial"] == "ON"]
    off = [r for r in rows if r["true_initial"] == "OFF"]

    summary = {
        "scope": "E5-B read-only preflight; E5-A archived episode reuse",
        "states": len(rows),
        "true_on": len(on),
        "true_off": len(off),
        "complete_decisions": dict(
            Counter(r["conditional_complete_decision"] for r in rows)
        ),
        "unsealed_decisions": dict(
            Counter(r["unsealed_decision"] for r in rows)
        ),
        "runtime_only_decisions": dict(
            Counter(r["runtime_only_decision"] for r in rows)
        ),
        "receipt_sufficient": sum(
            bool(r["conditional_sufficient"]) for r in rows
        ),
        "on_with_successful_target_on": sum(
            any(
                e["action"] == "ToggleObjectOn"
                and e["success"] is True
                for e in r["target_toggle_events"]
            )
            for r in on
        ),
        "off_without_target_power_receipt": sum(
            len(r["target_toggle_events"]) == 0
            for r in off
        ),
        "assumptions": [
            "Evaluator setup receipts allowed only under explicit T0 upper bound",
            "Complete ordered single-writer trace is assumed, not authenticated",
            "No OFF state inferred from missing power actions",
            "No physical sensor independence or deployment ACL verified"
        ],
    }

    write_json(out / "summary.json", summary)
    finish_hashes(out)

    print("\n===== E5-B SOURCE AUDIT =====")
    for key, value in summary.items():
        if key != "assumptions":
            print(f"{key}: {value}")

    print("\nE5-B RECEIPT PREFLIGHT: COMPLETED")
    print("Output:", out)


if __name__ == "__main__":
    main()
