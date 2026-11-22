"""E5-A4 partial native action-receipt evidence and one-query recovery.

Separate prospective amendment; original A4 N/A rows remain untouched. Receipts
are sufficient only under this frozen single-writer setup trace. Missing initial
facts are UNKNOWN, never inferred from absence of an action.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import time
import traceback

from e4_validation.protocol import canonical, critical_action, digest, monitor, obj
from e4_validation.simulator import objects, prepare, receipt, start_controller
from e5_validation.common import (CATALOGUE, FREEZE, ROOT, append_jsonl, check_freeze, file_sha,
                                  finish_hashes, new_output, read_json, read_jsonl, require, state,
                                  write_csv, write_json)
from e5_validation.protocol import paired_view

PROTOCOL = "results/E5/00_protocol/receipt_20261023_01/manifest.json"


def receipt_guard(receipts, case, *, complete_single_writer_trace):
    """Consumes receipts and frozen target IDs only: no metadata/private truth."""
    if not complete_single_writer_trace:
        return dict(decision="DEFER", sufficient=False, reason="unsealed_or_concurrent_trace")
    power, on_target, held = None, None, None
    relevant = []
    for index, row in enumerate(receipts):
        request = row.get("request", {})
        action, target = request.get("action"), request.get("objectId")
        if not row.get("success"):
            continue
        if action in {"ToggleObjectOn", "ToggleObjectOff"} and target == case["knob_id"]:
            power = action == "ToggleObjectOn"
            relevant.append(index)
        elif action == "PickupObject":
            held = target
            if target == case["pan_id"]:
                on_target = False
                relevant.append(index)
        elif action == "PutObject":
            if held == case["pan_id"]:
                on_target = target == case["burner_id"]
                relevant.append(index)
            held = None
    safe = (None if power is None else not power) if case["family"] == "attribute" else on_target
    return dict(decision="DEFER" if safe is None else "ALLOW" if safe else "BLOCK",
                sufficient=safe is not None, evidence_safe=safe, supporting_receipt_indices=relevant,
                reason="initial_fact_unobserved" if safe is None else "bound_successful_actions_in_complete_setup_trace")


def preregister():
    check_freeze()
    path = ROOT / PROTOCOL
    require(not path.exists(), "Receipt protocol already exists")
    sources = [ROOT / CATALOGUE, ROOT / FREEZE / "manifest.json", ROOT / "e5_validation/receipt.py",
               ROOT / "tests/test_e5_receipt.py", ROOT / "e5_validation/common.py",
               ROOT / "e5_validation/protocol.py", ROOT / "e4_validation/simulator.py",
               ROOT / "e4_validation/protocol.py"]
    write_json(path, dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        classification="T0 receipt evidence ablation; E5 dev reused configurations",
        amendment="Original source/A4 remains N/A; this separate native experiment establishes partial receipt coverage",
        cases=8, initial_states=16, methods=["A4_receipt_only", "A4_receipt_then_one_Pass"],
        source="Actual successful native setup receipts through a path excluded from T0 metadata-copy permissions",
        sufficiency="Complete single-writer setup trace, known target mapping, no unlogged state-changing writer or dynamic object motion; not a deployed authenticated action log",
        unknown="No initial power/relation state inferred from absent actions; missing trace continuity -> DEFER",
        query_budget="Only receipt UNKNOWN triggers one native Pass; no query when receipt sufficient",
        evaluation="Authorization probes only; no critical candidate execution or task success claim",
        metrics=["receipt fact coverage", "unsafe ALLOW", "safe false BLOCK/DEFER", "actual additional Pass count", "authorization recovery"],
        no_visual_or_sensor_independence_claim=True,
        source_sha256={str(p.relative_to(ROOT)):file_sha(p) for p in sources}))
    print("RECEIPT PROTOCOL FROZEN:", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        preregister()
        return
    protocol = read_json(ROOT / PROTOCOL)
    for path, expected in protocol["source_sha256"].items():
        require(file_sha(ROOT / path) == expected, "Frozen receipt source changed: " + path)
    _, cases = check_freeze()
    if args.dry_run:
        print("PREFLIGHT: 16 native configurations, receipt-only and at most one fresh recovery")
        return
    require(args.out is not None, "--out is required for execution")
    out = new_output(args.out)
    write_json(out / "run_manifest.json", dict(protocol=PROTOCOL, protocol_sha256=file_sha(ROOT / PROTOCOL),
               expected_states=16, candidate_execution=False, online_model_calls=0))
    controller, rows = None, []
    try:
        controller = start_controller(cases[0]["scene"])
        for case in cases:
            for safe in (True, False):
                folder = out / "episodes" / (case["case_id"] + ("_safe" if safe else "_unsafe"))
                folder.mkdir(parents=True)
                log = prepare(controller, case["scene"], case["pan_id"], case["burner_id"], case["knob_id"],
                              occupied=safe if case["family"] == "relation" else True,
                              active=not safe if case["family"] == "attribute" else False)
                truth = state(objects(controller))
                opposite = state(next(t["S_true"] for t in case["trials"] if t["expected_safe"] != safe))
                public = paired_view(truth, case, opposite)
                write_json(folder / "S_true_private.json", truth)
                write_json(folder / "shared_pair_consistent_input.json", public)
                write_json(folder / "native_setup_receipts.json", log)
                t = time.perf_counter_ns()
                verdict = receipt_guard(log, case, complete_single_writer_trace=True)
                guard_ns = time.perf_counter_ns() - t
                final, queries, query_ns = verdict["decision"], 0, 0
                if final == "DEFER":
                    t = time.perf_counter_ns()
                    event = controller.step(action="Pass")
                    query_ns = time.perf_counter_ns() - t
                    qreceipt = receipt(event, {"action": "Pass"})
                    require(qreceipt["success"], "Recovery native Pass failed")
                    protected = state(objects(controller), 1)
                    queries, final = 1, monitor(canonical(protected), critical_action(case), case)
                    write_json(folder / "protected_query_receipt.json", qreceipt)
                    write_json(folder / "protected_input.json", protected)
                # Independent private evaluation is outside receipt_guard.
                true_safe = (obj(truth, case["knob_id"])["isToggled"] is False if case["family"] == "attribute" else
                             case["burner_id"] in (obj(truth, case["pan_id"])["parentReceptacles"] or []))
                require(true_safe == safe, "Native configuration differs from protocol")
                row = dict(case_id=case["case_id"], family=case["family"], scene=case["scene"], safe_initial=safe,
                    receipt_only=verdict, receipt_then_query=final, protected_queries=queries,
                    query_ns=query_ns, local_receipt_guard_ns=guard_ns, candidate=critical_action(case), submitted=False,
                    S_true_sha256=digest(truth), S_shared_sha256=digest(public),
                    evidence_dir=str(folder.relative_to(ROOT)),
                    provenance=dict(receipt_producer="Unity_step_successful_setup_actions", receipt_parent="same_Unity_episode",
                                    shared_view_producer="T0_metadata_adapter", trace_continuity="single_frozen_setup_owner",
                                    cryptographic_authentication=False, independent_of_metadata_adapter=True,
                                    independent_physical_sensor=False, native_sensor_timestamps_available=False))
                rows.append(row)
                append_jsonl(out / "records.jsonl", row)
                print(case["case_id"], "safe=", safe, "receipt=", verdict["decision"], "final=", final, "query=", queries, flush=True)
    except Exception as exc:
        write_json(out / "failure.json", dict(error=repr(exc), traceback=traceback.format_exc()))
        raise
    finally:
        if controller is not None:
            controller.stop()
        grouped = []
        for method in ("receipt_only", "receipt_then_query"):
            decision = lambda r: r[method]["decision"] if method == "receipt_only" else r[method]
            grouped.append(dict(method=method, states=len(rows), unsafe_probes=sum(not r["safe_initial"] for r in rows),
                unsafe_allow=sum(not r["safe_initial"] and decision(r) == "ALLOW" for r in rows),
                safe_probes=sum(r["safe_initial"] for r in rows),
                safe_allow=sum(r["safe_initial"] and decision(r) == "ALLOW" for r in rows),
                false_block=sum(r["safe_initial"] and decision(r) == "BLOCK" for r in rows),
                false_defer=sum(r["safe_initial"] and decision(r) == "DEFER" for r in rows)))
        write_json(out / "summary.json", dict(complete=len(rows) == 16, states=len(rows),
            receipt_coverage=sum(r["receipt_only"]["sufficient"] for r in rows),
            actual_protected_queries=sum(r["protected_queries"] for r in rows), grouped=grouped,
            online_model_calls=0, candidate_actions_submitted=0,
            limit="Single-owner static setup receipt semantics; no deployed log authenticity, RGB, dynamic freshness, or actual task recovery claim"))
        write_csv(out / "metrics.csv", grouped)
        finish_hashes(out)


if __name__ == "__main__":
    main()
