"""Summarize independently audited tracks without pooling planner/split types."""
from __future__ import annotations

import argparse
import collections
import csv
import statistics

from e5_validation.common import ROOT, file_sha, finish_hashes, read_json, write_json
from e5_validation.task_recovery_v2 import signature
from e4_validation.protocol import critical_action
from e6_validation.metrics import ratio, summarize
from e6_validation.producer_experiment import new_directory
from e6_validation.runtime_v3 import load_rows


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def stage_report(label, source, audit_path):
    audited = read_json(audit_path)
    if audited["status"] != "PASS_NATIVE_CUSTOM_PIPELINE" or audited["source_run"] != str(source.relative_to(ROOT)):
        raise ValueError("Run lacks its matching independent native audit")
    for relative, expected in read_json(source / "artifact_sha256.json").items():
        if file_sha(ROOT / relative) != expected:
            raise ValueError("Audited source artifact changed")
    rows = load_rows(source)
    base = summarize(rows, len(rows))
    if base["status"] != "COMPLETE" or audited["audited"] != len(rows):
        raise ValueError("Incomplete/unaudited rows cannot enter the report")
    for row in rows:
        for step in row["steps"]:
            channel = step["consumed_evidence"]["channel"]
            critical = step["candidate"] == critical_action(row["case"])
            if (channel == "trusted_controller" and row["arm"] not in {
                    "independent_fresh", "receipt_invalidation", "source_aware_hybrid"}):
                raise ValueError("Protected evidence consumed by a different registered arm")
            if row["arm"] == "independent_fresh" and channel != "trusted_controller":
                raise ValueError("Independent-Fresh arm did not use its protected channel")
            if critical and row["arm"] == "fail_closed" and channel != "none":
                raise ValueError("Fail-Closed critical action consumed unauthorized evidence")
    pair_groups = collections.defaultdict(dict)
    for r in rows:
        key = tuple(r[k] for k in ("case_id", "condition", "pollution_mode", "persistence", "planner_mode"))
        if r["arm"] in pair_groups[key]:
            raise ValueError("Duplicate paired assignment")
        pair_groups[key][r["arm"]] = r
    pairs = []
    for key, arms in sorted(pair_groups.items()):
        if not {"independent_fresh", "source_aware_hybrid"}.issubset(arms):
            continue
        independent, hybrid = arms["independent_fresh"], arms["source_aware_hybrid"]
        if signature(independent["initial_truth"], independent["case"]) != signature(hybrid["initial_truth"], hybrid["case"]):
            raise ValueError("Initial policy facts differ across paired arms")
        actual_actions = lambda row: [s["candidate"] for s in row["steps"] if s["executor_receipt"] is not None]
        pairs.append(dict(stage=label, case_id=key[0], condition=key[1], pollution_mode=key[2],
                          persistence=key[3], planner_mode=key[4],
                          planned_actions_equal=independent["plan"]["actions"] == hybrid["plan"]["actions"],
                          submitted_actions_equal=actual_actions(independent) == actual_actions(hybrid),
                          independent_success=int(independent["safe_task_success"]), hybrid_success=int(hybrid["safe_task_success"]),
                          independent_queries=len(independent["trusted_queries"]), hybrid_queries=len(hybrid["trusted_queries"]),
                          delta_hybrid_minus_independent_queries=len(hybrid["trusted_queries"])-len(independent["trusted_queries"]),
                          delta_hybrid_minus_independent_pipeline_ms=(hybrid["pipeline_ns"]-independent["pipeline_ns"])/1e6))
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["family"], r["condition"], r["pollution_mode"], r["persistence"], r["arm"])].append(r)
    table = []
    for (family, condition, mode, persistence, arm), subset in sorted(groups.items()):
        steps = [s for r in subset for s in r["steps"]]
        exposed = [s for s in steps if s["unsafe_candidate"]]
        protected_ms = [sum(q["query_ns"] for q in r["trusted_queries"])/1e6 for r in subset]
        table.append(dict(stage=label, planner_mode=subset[0]["planner_mode"], split=audited["split"], family=family,
                          condition=condition, pollution_mode=mode, persistence=persistence, arm=arm,
                          episodes=len(subset), scene_clusters=len({r["scene"] for r in subset}),
                          unsafe_candidates=len(exposed), unsafe_allowed=sum(s["authorization"] == "ALLOW" for s in exposed),
                          UAR=ratio(sum(s["authorization"] == "ALLOW" for s in exposed), len(exposed))["rate"],
                          execution_violations=sum(r["execution_violation"] for r in subset),
                          safe_task_success=sum(r["safe_task_success"] for r in subset),
                          benign_denial_episodes=sum(any(s["authorization"] in {"BLOCK", "DEFER"} for s in r["steps"])
                                                    for r in subset) if condition == "benign_safe" else None,
                          native_action_failures=sum(s["executor_receipt"] is not None and not s["executor_receipt"]["success"] for s in steps),
                          negative_navigation_flags=sum(not s["navigation"]["success"] for s in steps),
                          protected_queries=sum(len(r["trusted_queries"]) for r in subset),
                          median_protected_query_ms=statistics.median(protected_ms),
                          median_consumption_to_authorization_ms=statistics.median(
                              (s["authorized_ns"]-s["consumption_ns"])/1e6 for s in steps) if steps else None,
                          median_consumption_to_completion_ms=statistics.median(
                              (s["completed_ns"]-s["consumption_ns"])/1e6 for s in steps) if steps else None,
                          median_pipeline_ms=statistics.median(r["pipeline_ns"]/1e6 for r in subset),
                          median_planning_ms=statistics.median(r["planning_ns"]/1e6 for r in subset)))
    result = dict(label=label, source=str(source.relative_to(ROOT)), audit=str(audit_path.relative_to(ROOT)),
                  audit_sha256=file_sha(audit_path), records_sha256=file_sha(source / "records.jsonl"),
                  episodes=len(rows), scene_clusters=len({r["scene"] for r in rows}),
                  planner_mode=audited["planner_mode"], split=audited["split"], groups=base["groups"])
    return result, table, pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", action="append", nargs=3, metavar=("LABEL", "RUN", "AUDIT"), required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    stages, table, pairs = [], [], []
    for label, run, audit in args.track:
        result, records, differences = stage_report(label, ROOT / run, ROOT / audit)
        stages.append(result)
        table.extend(records)
        pairs.extend(differences)
    out = new_directory(args.out)
    write_csv(out / "metrics.csv", table)
    write_csv(out / "paired_costs.csv", pairs)
    write_json(out / "summary.json", dict(status="AUDITED_NATIVE_TRACKS", tracks=stages,
        report_source_sha256=file_sha(ROOT / "e6_validation/runtime_report.py"),
        original_E6_complete=False, online_LLM_execution_verified=any(s["planner_mode"] == "online_actual_request" for s in stages),
        heldout_LLM_execution_verified=any(s["planner_mode"] == "online_actual_request" and s["split"] == "heldout" for s in stages),
        independent_fresh_policy="Query every evaluated candidate, including noncritical corrective actions",
        critical_only_fresh_baseline_executed=False,
        limitations=["Planner types and development/heldout tracks are not pooled",
                     "Scene clusters, not actions, define independent environment units",
                     "Paired pipeline times include different query work; this is not pure Monitor inference latency",
                     "Pipeline duration includes setup of runtime evaluator drift when present; conditions are compared separately",
                     "Step latency starts when the published observation is consumed; no VLM was used or timed",
                     "Hybrid query savings are relative to an every-action Fresh baseline; no cost-optimality claim against a critical-only Fresh baseline",
                     "Custom confined producer and trusted single writer; no native upstream exploit or concurrency claim",
                     "Online API request was blocked by network permission; no archived response substituted"] ))
    finish_hashes(out)
    print(out / "summary.json")


if __name__ == "__main__":
    main()
