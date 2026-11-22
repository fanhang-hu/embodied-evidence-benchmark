"""Offline post-experiment E5 phase-1 audit and report. Does not alter frozen runners."""
from __future__ import annotations

import argparse
import collections
import statistics

from e4_validation.protocol import canonical, critical_action, digest, monitor, obj
from e5_validation.common import (ROOT, append_jsonl, check_freeze, file_sha, finish_hashes,
                                  new_output, read_json, read_jsonl, require, write_csv, write_json)
from e5_validation.receipt import receipt_guard
from e5_validation.verify import check_graph, verify_binding, verify_source

SOURCE = ROOT / "results/E5/source/native_20261023_01"
BINDING = ROOT / "results/E5/binding/native_20261023_02"
RECEIPT = ROOT / "results/E5/source/receipt_native_20261023_01"


def receipt_audit(cases):
    manifest = read_json(RECEIPT / "run_manifest.json")
    protocol = read_json(ROOT / manifest["protocol"])
    require(file_sha(ROOT / manifest["protocol"]) == manifest["protocol_sha256"], "Receipt protocol changed")
    for name, expected in protocol["source_sha256"].items():
        require(file_sha(ROOT / name) == expected, "Receipt source changed: " + name)
    for name, expected in read_json(RECEIPT / "artifact_sha256.json").items():
        require(file_sha(ROOT / name) == expected, "Receipt artifact changed: " + name)
    rows = read_jsonl(RECEIPT / "records.jsonl")
    source = {(r["case_id"], r["safe_initial"]): r for r in read_jsonl(SOURCE / "records.jsonl") if r["arm"] == "A2_pair_consistent"}
    require(len(rows) == len(source) == 16, "Receipt controls incomplete")
    require(len({(r["case_id"], r["safe_initial"]) for r in rows}) == 16, "Duplicate receipt condition")
    for row in rows:
        case, folder = cases[row["case_id"]], ROOT / row["evidence_dir"]
        truth = read_json(folder / "S_true_private.json")
        public = read_json(folder / "shared_pair_consistent_input.json")
        require(digest(truth) == row["S_true_sha256"] and digest(public) == row["S_shared_sha256"], "Receipt input hashes changed")
        log = read_json(folder / "native_setup_receipts.json")
        require(receipt_guard(log, case, complete_single_writer_trace=True) == row["receipt_only"], "Receipt-only decision changed")
        final = row["receipt_only"]["decision"]
        require(row["protected_queries"] == int(final == "DEFER"), "Receipt query budget not conditional")
        if row["protected_queries"]:
            receipt = read_json(folder / "protected_query_receipt.json")
            require(receipt["success"] and receipt["request"] == {"action": "Pass"}, "Recovery query did not occur")
            protected = read_json(folder / "protected_input.json")
            final = monitor(canonical(protected), critical_action(case), case)
        require(final == row["receipt_then_query"], "Receipt recovery decision changed")
        safe = (obj(truth, case["knob_id"])["isToggled"] is False if case["family"] == "attribute" else
                case["burner_id"] in (obj(truth, case["pan_id"])["parentReceptacles"] or []))
        require(safe == row["safe_initial"] and row["submitted"] is False, "Receipt true initial state or execution claim wrong")
        # Across native replays, compare critical facts, not volatile full metadata.
        old = source[(row["case_id"], row["safe_initial"])]
        old_truth = read_json(ROOT / old["S_true_private_path"])
        for object_id, field in [(case["knob_id"], "isToggled"), (case["burner_id"], "isToggled"),
                                 (case["pan_id"], "isPickedUp")]:
            require(obj(truth, object_id)[field] == obj(old_truth, object_id)[field], "Receipt paired critical fact mismatch")
        require(sorted(obj(truth, case["pan_id"]).get("parentReceptacles") or []) ==
                sorted(obj(old_truth, case["pan_id"]).get("parentReceptacles") or []), "Receipt paired parent relation mismatch")
    return rows


def percentiles(values):
    values = sorted(values)
    return dict(n=len(values), p50_ms=statistics.median(values) / 1e6 if values else None,
                p95_nearest_rank_ms=values[max(0, (95 * len(values) + 99)//100 - 1)]/1e6 if values else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    protocol, catalogue = check_freeze()
    cases = {c["case_id"]: c for c in catalogue}
    audits = dict(source=verify_source(SOURCE, cases), binding=verify_binding(BINDING, cases, protocol))
    receipt_rows = receipt_audit(cases)
    source_rows = read_jsonl(SOURCE / "records.jsonl")
    binding_rows = read_jsonl(BINDING / "records.jsonl")
    out = new_output(args.out)
    audits["receipt"] = dict(status="PASS", states=len(receipt_rows),
        receipt_fact_coverage=sum(r["receipt_only"]["sufficient"] for r in receipt_rows),
        actual_protected_queries=sum(r["protected_queries"] for r in receipt_rows), candidate_actions_submitted=0)
    write_json(out / "audit.json", audits)
    write_csv(out / "source_metrics.csv", read_json(SOURCE / "summary.json")["grouped"])
    write_csv(out / "binding_metrics.csv", read_json(BINDING / "summary.json")["grouped"])
    write_csv(out / "receipt_metrics.csv", read_json(RECEIPT / "summary.json")["grouped"])
    # Derived value-enriched manifest. Original manifests remain immutable.
    enriched = []
    for run in (SOURCE, BINDING):
        prefix = str(run.relative_to(ROOT)) + ":"
        for original in read_jsonl(run / "evidence_manifest.jsonl"):
            row = dict(original)
            row["evidence_id"] = prefix + original["evidence_id"]
            row["parent_source_ids"] = [prefix + p for p in original["parent_source_ids"]]
            row["source_manifest"] = str((run / "evidence_manifest.jsonl").relative_to(ROOT))
            payload = read_json(ROOT / row["snapshot_path"])
            case = next(c for c in catalogue if c["scene"] == row["scene_id"] and c["pan_id"] == row["object_id"]
                        and ((c["family"] == "attribute") == (row["predicate"] == "bound_power_off")))
            row["value"] = (obj(payload, case["knob_id"])["isToggled"] is False if case["family"] == "attribute" else
                            case["burner_id"] in (obj(payload, case["pan_id"]).get("parentReceptacles") or []))
            enriched.append(row)
    for row in receipt_rows:
        case = cases[row["case_id"]]
        folder = ROOT / row["evidence_dir"]
        prefix = row["evidence_dir"] + ":"
        root_id = prefix + "single_owner_Unity_episode"
        enriched.append(dict(evidence_id=root_id, parent_source_ids=[], producer_id="Unity_episode",
                             scene_id=case["scene"], episode_id=folder.name,
                             object_id=case["pan_id"], target_id=case["burner_id"],
                             allowed_to_defender=False, value="underlying_episode_not_a_guard_input"))
        enriched.append(dict(evidence_id=prefix + "receipt", parent_source_ids=[root_id],
            producer_id="Unity_successful_action_receipts", scene_id=case["scene"], episode_id=folder.name,
            object_id=case["pan_id"], target_id=case["burner_id"],
            predicate="policy_safe_under_sealed_trace", value=row["receipt_only"].get("evidence_safe"),
            observation_type="native_action_receipt", allowed_to_defender=True,
            source_traceable=True, cryptographic_authentication=False,
            uncorrupted_under_threat_model=True, independent_physical_sensor=False,
            evidence_trust="receipt_branch_protected_under_T0", collection_monotonic_ns=None,
            received_monotonic_ns=None, native_sensor_timestamps_available=False,
            snapshot_path=str((folder / "native_setup_receipts.json").relative_to(ROOT)),
            snapshot_sha256=file_sha(folder / "native_setup_receipts.json"), hash_semantics="file_bytes",
            coverage_sufficient=row["receipt_only"]["sufficient"],
            validity_assumption="complete_single_owner_static_setup_only"))
        if row["protected_queries"]:
            enriched.append(dict(evidence_id=prefix + "recovery_Pass", parent_source_ids=[root_id],
                producer_id="Unity_protected_Pass", scene_id=case["scene"], episode_id=folder.name,
                object_id=case["pan_id"], target_id=case["burner_id"],
                value=row["receipt_then_query"] == "ALLOW", allowed_to_defender=True,
                snapshot_path=str((folder / "protected_input.json").relative_to(ROOT)),
                snapshot_sha256=file_sha(folder / "protected_input.json"), hash_semantics="file_bytes",
                evidence_trust="X_protected_native", native_sensor_timestamps_available=False,
                collection_monotonic_ns=None, received_monotonic_ns=None))
    for row in enriched:
        for key, default in dict(schema="e5.evidence.v1", predicate="source_episode",
            collection_monotonic_ns=None, received_monotonic_ns=None, validity_interval_ns=None,
            state_version=None, observation_type="provenance_source_node", image_sha256=None,
            attackable_fields=[], attacker_level="T0", evidence_trust="not_a_guard_input",
            observability="not_applicable_or_recorded_in_snapshot", source_traceable=True,
            cryptographic_authentication=False,
            private_evaluator_truth="SEPARATE_FILE_NEVER_IN_MODEL_PROMPT").items():
            row.setdefault(key, default)
    check_graph(enriched)
    for row in enriched:
        append_jsonl(out / "evidence_manifest.jsonl", row)
    write_json(out / "cost_observations.json", dict(
        A5_actual_queries=16, A6_budget1_actual_queries=16,
        receipt_conditional_actual_queries=sum(r["protected_queries"] for r in receipt_rows),
        A5_query_time=percentiles([r["protected_query_ns"] for r in source_rows if r["arm"] == "A5_protected_query"]),
        receipt_recovery_query_time=percentiles([r["query_ns"] for r in receipt_rows if r["protected_queries"]]),
        receipt_local_guard_time=percentiles([r["local_receipt_guard_ns"] for r in receipt_rows]),
        binding_query_time=percentiles([r["query_ns"] for r in binding_rows if r["method"] == "E1_exact_membership"]),
        interpretation="Actual Pass counts exclude setup/navigation RPCs. Same frozen critical state configurations in separate native replays, not same physical instant. Query time is Controller.step(Pass) only. No online LLM or task completion latency claimed."))
    failures = read_json(ROOT / "results/E5/binding/native_20261023_01/failure.json")
    write_json(out / "retained_engineering_attempts.json", dict(
        run="results/E5/binding/native_20261023_01", complete_controls=5, attempted_controls=6,
        invalid_controls=1, unattempted_controls=3, partial_decisions=30,
        error=failures["error"], resolution="Prospective v2 selects a decoy empty in frozen pre-E5 initial metadata; all three cases retained",
        counted_as_additional_independent_samples=False))
    write_json(out / "stage_readiness.json", dict(
        status="E5_A_E_METADATA_RECEIPT_PILOT_COMPLETE", overall_E5_scope="partial; no visual/dynamic/deployment claim",
        classification="T0 controlled-copy only", split="E5_dev_reuse_E4_small_heldout",
        source_task_configurations=8, source_scene_clusters=4, binding_task_configurations=3,
        binding_physical_controls=9, candidate_execution_tested=False, online_model_calls=0,
        A4_status="Original unavailable arm retained; separate partial native receipt evidence plus one-query recovery completed",
        independent_visual_or_ROI_tested=False, native_T1_T2_demonstrated=False,
        complex_new_monitor_justified=False,
        stop_reason="Protected native facts cover all eight dangerous and eight legal initial probes; partial receipt evidence reduces actual additional Pass demand from 16 to 8 in these paired configurations",
        remaining=["Deployment availability/authenticity of protected facts and receipt continuity remains assumed",
                   "No RGB/ROI or independent physical sensor evaluation; do only if a concrete coverage gap justifies it",
                   "Dynamic staleness/conflict/occlusion B/C/D need natural trigger and prospective protocol; not fabricated",
                   "New two-field conditions evaluated as authorization probes, not new Unity violation execution or actual task recovery"],
        E6_started=False))
    sources = {}
    for run in (SOURCE, BINDING, RECEIPT):
        for path in run.rglob("*"):
            if path.is_file():
                sources[str(path.relative_to(ROOT))] = file_sha(path)
    for path in (ROOT / "results/E5/00_protocol").rglob("manifest.json"):
        sources[str(path.relative_to(ROOT))] = file_sha(path)
    sources["e5_validation/report.py"] = file_sha(ROOT / "e5_validation/report.py")
    write_json(out / "source_artifacts_sha256.json", sources)
    finish_hashes(out)
    print("E5 PHASE-1 AUDIT PASS:", out, "; enriched evidence nodes:", len(enriched))


if __name__ == "__main__":
    main()
