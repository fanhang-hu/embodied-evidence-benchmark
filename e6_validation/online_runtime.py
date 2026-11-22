"""Checkpointed online E6 runner with durable call budgets and stop-on-failure."""
from __future__ import annotations

import argparse
import datetime
import fcntl
import time
from pathlib import Path

from e4_validation.simulator import start_controller
from e5_validation.common import ROOT, file_sha, finish_hashes, read_json
from e6_validation.metrics import summarize
from e6_validation.online_session import JournalPlanner, durable_json, error_record, provider_config
from e6_validation.producer_experiment import new_directory
from e6_validation.runtime_v3 import check_protocol as check_parent, load_rows, run_episode


SOURCES = ("e6_validation/online_session.py", "e6_validation/online_runtime.py",
           "e6_validation/online_audit.py", "e6_validation/evidence_checks.py",
           "e6_validation/runtime_v4.py", "e6_validation/runtime_audit_v4.py")


def freeze(args):
    parent_path = (ROOT / args.parent).resolve()
    parent = check_parent(parent_path)
    if parent["planner_mode"] != "online_actual_request":
        raise ValueError("Expected an existing frozen online assignment matrix")
    protocol = dict(parent, schema="e6.online.v1", parent_protocol=str(parent_path.relative_to(ROOT)),
                    parent_sha256=file_sha(parent_path), provider_config=provider_config(),
                    created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    failure_policy="Stop batch on first failed episode; retain it and resume next assignment",
                    interruption_policy="Reserved/started uncommitted episode becomes INTERRUPTED; never retry/replay",
                    source_sha256=dict(parent["source_sha256"], **{s: file_sha(ROOT / s) for s in SOURCES}))
    out = new_directory(args.out)
    durable_json(out / "protocol.json", protocol)
    print(out / "protocol.json")


def check_protocol(path):
    protocol = read_json(path)
    if protocol["schema"] != "e6.online.v1":
        raise ValueError("Expected durable online protocol")
    parent_path = ROOT / protocol["parent_protocol"]
    if file_sha(parent_path) != protocol["parent_sha256"]:
        raise ValueError("Parent protocol changed")
    parent = check_parent(parent_path)
    for key in ("assignments", "cases", "expected", "split", "planner_mode", "online_call_budget"):
        if protocol[key] != parent[key]:
            raise ValueError("Online amendment changed the experimental matrix")
    for name, expected in protocol["source_sha256"].items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    return protocol


def committed_rows(out, protocol):
    rows = []
    for path in sorted((out / "episodes").glob("*.json")):
        row = read_json(path)
        index = len(rows)
        if (index >= protocol["expected"] or path.name != f"{index:04d}.json"
                or row["episode_index"] != index
                or any(row[k] != v for k, v in protocol["assignments"][index].items())):
            raise ValueError("Committed episode identity/order mismatch")
        rows.append(row)
    return rows


def commit(out, row):
    durable_json(out / "episodes" / f"{row['episode_index']:04d}.json", row)


def failure_row(protocol, index, status, **extra):
    assignment = protocol["assignments"][index]
    case = next(c for c in protocol["cases"] if c["case_id"] == assignment["case_id"])
    return dict(assignment, episode_index=index, status=status, case=case,
                planner_mode="online_actual_request", execution_violation=None,
                safe_task_success=None, **extra)


def reconcile(out, protocol, planner):
    rows = committed_rows(out, protocol)
    indexed = load_rows(out)
    if rows[:len(indexed)] != indexed or not 0 <= len(rows)-len(indexed) <= 1:
        raise ValueError("Committed rows differ from prior checkpoint or contain unexpected unindexed results")
    calls = planner.inventory()
    starts = sorted((out / "starts").glob("*.json"))
    indices = [int(p.stem) for p in starts]
    if indices != list(range(len(starts))) or len(starts) > protocol["expected"]:
        raise ValueError("Started episode sequence mismatch")
    for i, p in enumerate(starts):
        if read_json(p)["assignment"] != protocol["assignments"][i]:
            raise ValueError("Started assignment changed")
    if len(starts) < len(rows) or any(i >= len(starts) for i in calls):
        raise ValueError("Call/commit has no preceding episode start")
    for i in range(len(rows), len(starts)):
        row = failure_row(protocol, i, "INTERRUPTED", reason="Started episode lacks a committed result",
                          reserved_calls=int(i in calls), recovered_ns=time.perf_counter_ns())
        commit(out, row)
        rows.append(row)
    return rows


def checkpoint(out, rows, protocol, planner, stop_reason):
    entries = [dict(episode_index=i, episode_file=f"episodes/{i:04d}.json",
                    sha256=file_sha(out / "episodes" / f"{i:04d}.json")) for i in range(len(rows))]
    durable_json(out / "records.jsonl", entries, replace=True, lines=True)
    calls = planner.inventory()
    summary = summarize(rows, protocol["expected"])
    # Never present a completed subset as the registered matrix result.
    observed = summary.pop("groups")
    complete = summary["status"] == "COMPLETE"
    summary.update(groups=observed if complete else [], diagnostic_completed_subset=observed if not complete else [],
                   next_index=len(rows), split=protocol["split"], planner_mode=protocol["planner_mode"],
                   matrix_slots_accounted=len(rows), reserved_calls=len(calls),
                   successful_responses=sum(c["terminal"] is not None and c["terminal"]["status"] == "OK"
                                            for c in calls.values()),
                   failed_or_interrupted=sum(r["status"] != "COMPLETED" for r in rows), stop_reason=stop_reason)
    durable_json(out / "summary.json", summary, replace=True)
    finish_hashes(out)
    return summary


def run(args):
    path = (ROOT / args.protocol).resolve()
    protocol = check_protocol(path)
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to(ROOT / "results/E6"):
        raise ValueError("Output must be under results/E6")
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another runner holds this run's lock") from exc
        manifest_path = out / "run_manifest.json"
        manifest = dict(schema="e6.online.v1", protocol=str(path.relative_to(ROOT)),
                        protocol_sha256=file_sha(path), backend="native_Unity_headless_FIFO")
        if manifest_path.exists():
            if read_json(manifest_path) != manifest:
                raise ValueError("Resume protocol/backend mismatch")
        else:
            if any(p.name != ".run.lock" for p in out.iterdir()):
                raise ValueError("Unrecognized preexisting output directory")
            durable_json(manifest_path, manifest)
        planner = JournalPlanner(out / "online_calls", protocol, file_sha(path))
        rows = reconcile(out, protocol, planner)
        first = len(rows)
        controller, stop_reason = None, "BATCH_LIMIT"
        cases = {c["case_id"]: c for c in protocol["cases"]}
        try:
            if first < protocol["expected"]:
                controller = start_controller(protocol["cases"][0]["scene"])
            for i in range(first, min(first+args.limit, protocol["expected"])):
                assignment = protocol["assignments"][i]
                durable_json(out / "starts" / f"{i:04d}.json",
                             dict(assignment=assignment, started_ns=time.perf_counter_ns()))
                try:
                    row = run_episode(controller, cases[assignment["case_id"]], assignment,
                                      lambda public, case: planner.provide_for(i, public, case),
                                      "online_actual_request")
                    row["episode_index"] = i
                except Exception as exc:
                    row = failure_row(protocol, i, "FAILED_OR_INCOMPLETE", error=error_record(exc),
                                      reserved_calls=int(planner.request_path(i).exists()))
                commit(out, row)
                rows.append(row)
                checkpoint(out, rows, protocol, planner, "EPISODE_COMMITTED")
                print(f"{i+1}/{protocol['expected']} {assignment['case_id']} {row['status']}", flush=True)
                if row["status"] != "COMPLETED":
                    stop_reason = "STOP_ON_FAILURE"
                    break
        finally:
            try:
                if controller is not None:
                    controller.stop()
            finally:
                summary = checkpoint(out, rows, protocol, planner,
                                     "MATRIX_ACCOUNTED" if len(rows) == protocol["expected"] else stop_reason)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--parent", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("run")
    p.add_argument("--protocol", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()
    if args.command == "run" and args.limit < 1:
        raise ValueError("Batch limit must be positive")
    if args.command == "freeze":
        freeze(args)
    elif run(args)["failed_or_interrupted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
