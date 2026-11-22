"""Compare the added critical-only Fresh baseline with audited v3 controls.

Query counts are matched by configuration; cross-batch latency is descriptive.
The added episodes are not new independent scenes or online LLM evidence.
"""
from __future__ import annotations

import argparse
import collections
import statistics

from e4_validation.protocol import critical_action
from e5_validation.common import ROOT, file_sha, finish_hashes, read_json, write_json
from e5_validation.task_recovery_v2 import signature
from e6_validation.metrics import ratio, summarize
from e6_validation.producer_experiment import new_directory
from e6_validation.runtime_report import write_csv
from e6_validation.runtime_v3 import load_rows


ARMS = ("independent_fresh", "critical_only_fresh", "source_aware_hybrid")
KEYS = ("case_id", "condition", "pollution_mode", "persistence", "planner_mode")


def load_audited(run, audit_path):
    result = read_json(audit_path)
    if result["source_run"] != str(run.relative_to(ROOT)):
        raise ValueError("Audit belongs to a different source")
    for path, expected in read_json(run / "artifact_sha256.json").items():
        if file_sha(ROOT / path) != expected:
            raise ValueError("Source artifact changed: " + path)
    manifest = read_json(run / "run_manifest.json")
    path = ROOT / manifest["protocol"]
    if file_sha(path) != manifest["protocol_sha256"]:
        raise ValueError("Protocol hash mismatch")
    if manifest["schema"] == "e6.runtime.v4":
        from e6_validation.runtime_v4 import check_protocol
        from e6_validation.runtime_audit_v4 import audit
    else:
        from e6_validation.runtime_v3 import check_protocol
        from e6_validation.runtime_audit import audit
    protocol = check_protocol(path)
    repeated = audit(run, protocol)
    if any(result[k] != value for k, value in repeated.items()):
        raise ValueError("Independent audit result changed")
    rows = load_rows(run)
    for row in rows:
        for step in row["steps"]:
            channel = step["consumed_evidence"]["channel"]
            critical = step["candidate"] == critical_action(row["case"])
            if row["arm"] == "independent_fresh" and channel != "trusted_controller":
                raise ValueError("Every-action Fresh routing mismatch")
            if row["arm"] == "source_aware_hybrid" and channel != (
                    "trusted_controller" if critical else "producer_stdout"):
                raise ValueError("Hybrid routing mismatch")
    return rows, protocol, dict(run=str(run.relative_to(ROOT)), audit=str(audit_path.relative_to(ROOT)),
                               audit_sha256=file_sha(audit_path), protocol_sha256=file_sha(path),
                               artifacts_sha256=file_sha(run / "artifact_sha256.json"))


def compare(label, baseline_run, baseline_audit, controls_run, controls_audit):
    baseline, protocol, baseline_source = load_audited(baseline_run, baseline_audit)
    controls, control_protocol, controls_source = load_audited(controls_run, controls_audit)
    if any(protocol[k] != control_protocol[k] for k in ("cases", "split", "planner_mode")):
        raise ValueError("Cannot match different cases or planner tracks")
    if any(row["arm"] != "critical_only_fresh" for row in baseline):
        raise ValueError("Added baseline must contain only the prespecified arm")
    groups = collections.defaultdict(dict)
    for row in baseline + [r for r in controls if r["arm"] in ARMS]:
        key = tuple(row[k] for k in KEYS)
        if row["arm"] in groups[key]:
            raise ValueError("Duplicate matched condition")
        groups[key][row["arm"]] = row
    pairs, selected = [], []
    for key, arms in sorted(groups.items()):
        if set(arms) != set(ARMS):
            raise ValueError("Missing control or baseline: " + str(key))
        reference = arms["critical_only_fresh"]
        for arm, row in arms.items():
            if (signature(reference["initial_truth"], reference["case"])
                    != signature(row["initial_truth"], row["case"])
                    or reference["plan"]["actions"] != row["plan"]["actions"]
                    or reference["plan"]["prompt_sha256"] != row["plan"]["prompt_sha256"]):
                raise ValueError("Matched policy facts, prompt or planned actions differ")
            selected.append(row)
            if arm == "critical_only_fresh":
                continue
            def submitted(r):
                return [s["candidate"] for s in r["steps"] if s["executor_receipt"] is not None]
            pairs.append(dict(track=label, **dict(zip(KEYS, key)), comparator=arm,
                baseline_queries=len(reference["trusted_queries"]), comparator_queries=len(row["trusted_queries"]),
                delta_comparator_minus_baseline_queries=len(row["trusted_queries"])-len(reference["trusted_queries"]),
                submitted_actions_equal=submitted(reference) == submitted(row),
                baseline_success=reference["safe_task_success"], comparator_success=row["safe_task_success"],
                baseline_violation=reference["execution_violation"], comparator_violation=row["execution_violation"],
                baseline_pipeline_ms=reference["pipeline_ns"]/1e6, comparator_pipeline_ms=row["pipeline_ns"]/1e6))
    aggregate = []
    for condition in sorted({r["condition"] for r in selected}):
        for arm in ARMS:
            subset = [r for r in selected if r["condition"] == condition and r["arm"] == arm]
            steps = [s for r in subset for s in r["steps"]]
            dangerous = [s for s in steps if s["unsafe_candidate"]]
            critical = [s for r in subset for s in r["steps"] if s["candidate"] == critical_action(r["case"])]
            aggregate.append(dict(track=label, split=protocol["split"], planner_mode=protocol["planner_mode"],
                condition=condition, arm=arm, episodes=len(subset), scene_clusters=len({r["scene"] for r in subset}),
                unsafe_candidates=len(dangerous), unsafe_allowed=sum(s["authorization"] == "ALLOW" for s in dangerous),
                UAR=ratio(sum(s["authorization"] == "ALLOW" for s in dangerous), len(dangerous))["rate"],
                execution_violations=sum(r["execution_violation"] for r in subset),
                safe_task_success=sum(r["safe_task_success"] for r in subset),
                benign_denials=sum(any(s["authorization"] != "ALLOW" for s in r["steps"]) for r in subset)
                               if condition == "benign_safe" else None,
                critical_candidates=len(critical), trusted_critical_candidates=sum(
                    s["consumed_evidence"]["channel"] == "trusted_controller" for s in critical),
                protected_queries=sum(len(r["trusted_queries"]) for r in subset),
                native_action_failures=sum(s["executor_receipt"] is not None and not s["executor_receipt"]["success"] for s in steps),
                median_pipeline_ms=statistics.median(r["pipeline_ns"]/1e6 for r in subset),
                median_consumption_to_authorization_ms=statistics.median(
                    (s["authorized_ns"]-s["consumption_ns"])/1e6 for s in steps) if steps else None))
    return dict(label=label, baseline_source=baseline_source, controls_source=controls_source,
                added_episodes=len(baseline), matched_configurations=len(groups),
                split=protocol["split"], planner_mode=protocol["planner_mode"],
                groups=summarize(selected, len(selected))["groups"]), aggregate, pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", action="append", nargs=5, required=True,
                        metavar=("LABEL", "BASELINE", "BASELINE_AUDIT", "CONTROLS", "CONTROLS_AUDIT"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    tracks, aggregate, pairs = [], [], []
    for label, *paths in args.track:
        track, table, matched = compare(label, *(ROOT / p for p in paths))
        tracks.append(track)
        aggregate.extend(table)
        pairs.extend(matched)
    out = new_directory(args.out)
    write_csv(out / "metrics.csv", aggregate)
    write_csv(out / "matched_costs.csv", pairs)
    write_json(out / "summary.json", dict(status="AUDITED_MATCHED_CRITICAL_FRESH_COMPARISON", tracks=tracks,
        aggregate=aggregate, critical_only_fresh_baseline_executed=True,
        report_source_sha256=file_sha(ROOT / "e6_validation/critical_fresh_report.py"),
        original_E6_complete=False, online_LLM_execution_verified=False,
        limitations=["New baseline was run in a later batch; latency is descriptive, not a causal speed comparison",
                     "Identical policy facts, planner prompt and actions required for each matched configuration",
                     "Existing controls are reused, not new replications or independent scenes",
                     "Only the two frozen safety contracts are covered; noncritical actions still consume public evidence",
                     "No cost-optimality, attack-recovery, upstream exploit or concurrent-execution claim",
                     "Development archived LLM and heldout deterministic Planner tracks remain separate"] ))
    finish_hashes(out)
    print(out / "summary.json")


if __name__ == "__main__":
    main()
