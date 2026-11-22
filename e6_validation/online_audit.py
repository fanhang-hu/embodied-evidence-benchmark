"""Audit online reservations, interruption accounting and complete native matrices."""
from __future__ import annotations

import argparse
from pathlib import Path

from e4_validation.protocol import digest
from e5_validation.common import ROOT, file_sha, finish_hashes, read_json
from e6_validation.evidence_checks import verify_episode
from e6_validation.metrics import summarize
from e6_validation.online_runtime import check_protocol, committed_rows
from e6_validation.online_session import JournalPlanner
from e6_validation.producer_audit import require
from e6_validation.producer_experiment import new_directory
from e6_validation.runtime_audit_v4 import audit as audit_native
from e6_validation.runtime_v3 import load_rows
from e5_validation.common import write_json


def audit(run, protocol, protocol_hash):
    rows = load_rows(run)
    require(rows == committed_rows(run, protocol), "Checkpoint index differs from committed episodes")
    planner = JournalPlanner(run / "online_calls", protocol, protocol_hash)
    calls = planner.inventory()
    starts = sorted((run / "starts").glob("*.json"))
    require(len(starts) == len(rows) and all(p.name == f"{i:04d}.json" for i, p in enumerate(starts)),
            "Unreconciled started episode; resume before auditing")
    require(set(calls).issubset(range(len(rows))), "Call belongs to an unaccounted episode")
    for i, row in enumerate(rows):
        require(read_json(starts[i])["assignment"] == protocol["assignments"][i], "Start assignment mismatch")
        require(row["status"] in {"COMPLETED", "FAILED_OR_INCOMPLETE", "INTERRUPTED"}, "Unknown terminal status")
        if row["status"] != "COMPLETED":
            require(row["execution_violation"] is None and row["safe_task_success"] is None,
                    "Missing execution evidence reported as safe/successful")
            require(row["reserved_calls"] == int(i in calls), "Failure call budget mismatch")
            continue
        require(i in calls and calls[i]["terminal"] is not None
                and calls[i]["terminal"]["status"] == "OK", "Completed episode has no successful live response")
        call, plan = calls[i]["terminal"], row["plan"]
        require(plan["call_index"] == i and Path(plan["call_record"]).resolve() == planner.result_path(i).resolve()
                and plan["response"] == call["response"]
                and plan["request_sha256"] == call["request_sha256"]
                and call["public_state_sha256"] == digest(row["planner_input"]),
                "Planner response is not bound to this exact episode's call")
        require(row["planner_publication"]["received_ns"] <= call["request_ns"] <= call["response_ns"],
                "Live request predates published Planner input")
        if row["steps"]:
            require(call["response_ns"] <= row["steps"][0]["consumption_ns"], "Execution predates live response")
        verify_episode(row)
    expected = summarize(rows, protocol["expected"])
    summary = read_json(run / "summary.json")
    complete = expected["status"] == "COMPLETE"
    observed = expected.pop("groups")
    require(all(summary[k] == v for k, v in expected.items()), "Summary counts/status changed")
    require(summary["groups"] == (observed if complete else [])
            and summary["diagnostic_completed_subset"] == ([] if complete else observed),
            "Completed subset presented as full-matrix results")
    require(summary["reserved_calls"] == len(calls) and summary["next_index"] == len(rows)
            and summary["successful_responses"] == sum(
                c["terminal"] is not None and c["terminal"]["status"] == "OK" for c in calls.values())
            and summary["failed_or_interrupted"] == sum(r["status"] != "COMPLETED" for r in rows),
            "Persisted call/episode accounting differs from ledger")
    result = audit_native(run, protocol) if complete else dict(
        status="PASS_ACCOUNTING_ONLY", native_Unity_execution_verified=False,
        online_planning_verified=False, heldout_LLM_execution_verified=False, original_E6_complete=False)
    return dict(result, accounted_episodes=len(rows), expected=protocol["expected"],
                reserved_calls=len(calls), call_budget=protocol["online_call_budget"],
                matrix_fully_verified=complete)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run = (ROOT / args.run).resolve()
    for path, expected in read_json(run / "artifact_sha256.json").items():
        require(file_sha(ROOT / path) == expected, "Artifact changed: " + path)
    manifest = read_json(run / "run_manifest.json")
    path = ROOT / manifest["protocol"]
    require(file_sha(path) == manifest["protocol_sha256"], "Protocol hash mismatch")
    result = audit(run, check_protocol(path), file_sha(path))
    result["source_run"] = str(run.relative_to(ROOT))
    out = new_directory(args.out)
    write_json(out / "audit.json", result)
    finish_hashes(out)
    print(result)


if __name__ == "__main__":
    main()
