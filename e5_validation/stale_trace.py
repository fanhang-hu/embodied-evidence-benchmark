"""WP3: cached evidence after actual recorded native state transitions.

Post-hoc dev trace source, prospective condition/selection freeze. No new Unity
actions, no fabricated sensor age, and no natural-concurrency/TOCTOU claim.
"""
from __future__ import annotations

import argparse
import datetime

from e4_validation.protocol import canonical, critical_action, digest, monitor, obj
from e5_validation.common import (CATALOGUE, ROOT, append_jsonl, file_sha, finish_hashes,
                                  new_output, read_json, read_jsonl, require, write_csv, write_json)

RUN = "results/E5/task_recovery/native_20261023_02"
PROTOCOL = "results/E5/00_protocol/stale_trace_20261023_01/manifest.json"
CONDITIONS = ("T0_old_evidence_at_old_truth", "T1_stale_cache_at_new_truth", "T2_same_cache_reread",
              "T3_recorded_fresh_native_query", "T4_protected_single_writer_epoch_check")


def policy_safe(payload, case):
    if case["family"] == "attribute":
        return obj(payload, case["knob_id"])["isToggled"] is False
    return case["burner_id"] in (obj(payload, case["pan_id"]).get("parentReceptacles") or [])


def version_guard(cached, expected_epoch, candidate, case):
    if cached.get("state_version") != expected_epoch:
        return "DEFER"
    return monitor(canonical(cached), candidate, case)


def preregister():
    require(not (ROOT / PROTOCOL).exists(), "Stale-trace protocol already exists")
    run = ROOT / RUN
    require(read_json(run / "summary.json")["complete"], "Recovery trace incomplete")
    paths = [ROOT / "e5_validation/stale_trace.py", ROOT / "tests/test_e5_stale_trace.py", ROOT / CATALOGUE,
             run / "records.jsonl", run / "artifact_sha256.json", ROOT / "e4_validation/protocol.py"]
    write_json(ROOT / PROTOCOL, dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        split="E5_dev_posthoc_native_trace_reuse", source_outcomes_already_known=True,
        source=RUN, expected_case_configurations=8, conditions=list(CONDITIONS),
        selection={"attribute":"G0_clean, unsafe initial: first successful ToggleObjectOff followed immediately by another recorded protected guard query",
                   "relation":"G1_shared_no_recovery, safe initial: first successful PickupObject followed immediately by another recorded protected guard query"},
        evidence="Old actual protected query before transition; next actual protected query and private submission state after transition",
        time="Python adapter snapshot capture and native step order; no native sensor timestamp or chosen TTL",
        epoch="Protected single-owner application state_version from already recorded queries/receipts; not native global CAS/version or concurrent-writer proof",
        probe="Critical action authorization only; no new candidate submitted",
        source_sha256={str(p.relative_to(ROOT)):file_sha(p) for p in paths}))
    print("STALE TRACE DEV PROTOCOL FROZEN:", ROOT / PROTOCOL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.preregister:
        preregister()
        return
    protocol = read_json(ROOT / PROTOCOL)
    for name, expected in protocol["source_sha256"].items():
        require(file_sha(ROOT / name) == expected, "Stale trace input changed: " + name)
    for name, expected in read_json(ROOT / RUN / "artifact_sha256.json").items():
        require(file_sha(ROOT / name) == expected, "Recorded transition artifact changed")
    require(args.out, "--out is required")
    cases = read_jsonl(ROOT / CATALOGUE)
    source_rows = read_jsonl(ROOT / RUN / "records.jsonl")
    out = new_output(args.out)
    rows = []
    for case in cases:
        attribute = case["family"] == "attribute"
        arm = "G0_clean" if attribute else "G1_shared_no_recovery"
        selected = [r for r in source_rows if r["case_id"] == case["case_id"] and r["arm"] == arm
                    and r["safe_initial"] == (not attribute)]
        require(len(selected) == 1, "Ambiguous predeclared trace selection")
        episode = selected[0]
        desired_action = "ToggleObjectOff" if attribute else "PickupObject"
        index = next((i for i,s in enumerate(episode["steps"][:-1]) if s["candidate"]["action"] == desired_action
                      and s["action_success"] and episode["steps"][i+1]["guard_query"] is not None), None)
        require(index is not None, "Predeclared actual transition unavailable; do not select a replacement")
        old = read_json(ROOT / episode["steps"][index]["step_path"])
        new = read_json(ROOT / episode["steps"][index+1]["step_path"])
        cached, fresh = old["S_protected"], new["S_protected"]
        old_truth, new_truth = old["S_true_at_submission_private"], new["S_true_at_submission_private"]
        require(policy_safe(cached, case) == policy_safe(old_truth, case), "Old evidence was not correct when observed")
        require(policy_safe(cached, case) != policy_safe(new_truth, case), "No actual policy fact transition")
        require(policy_safe(fresh, case) == policy_safe(new_truth, case), "Fresh evidence wrong at new truth")
        require(old["executor_receipt"]["success"] and old["executor_receipt"]["request"]["forceAction"] is False,
                "No successful unforced native transition")
        require(new["guard_query"]["receipt"]["success"], "No actual fresh query")
        age_ns = new["guard_query"]["capture_monotonic_ns"] - old["guard_query"]["capture_monotonic_ns"]
        require(age_ns > 0 and fresh["state_version"] > cached["state_version"], "Invalid recorded cache chronology")
        candidate = critical_action(case)
        for condition in CONDITIONS:
            truth = old_truth if condition == CONDITIONS[0] else new_truth
            if condition == CONDITIONS[3]:
                verdict = monitor(canonical(fresh), candidate, case)
            elif condition == CONDITIONS[4]:
                verdict = version_guard(cached, fresh["state_version"], candidate, case)
            else:
                verdict = monitor(canonical(cached), candidate, case)
            row = dict(case_id=case["case_id"], family=case["family"], scene=case["scene"], condition=condition,
                safe_true=policy_safe(truth, case), final_authorization=verdict,
                candidate=candidate, submitted=False, actual_transition_action=old["candidate"],
                old_evidence_correct_at_capture=True, policy_fact_really_changed=True,
                old_input_sha256=digest(cached), fresh_input_sha256=digest(fresh),
                old_epoch=cached["state_version"], new_epoch=fresh["state_version"],
                recorded_adapter_snapshot_age_ns=age_ns, native_sensor_age_ns=None,
                old_step=episode["steps"][index]["step_path"], new_step=episode["steps"][index+1]["step_path"],
                split=protocol["split"], temporal_claim="sequential stale replay, not concurrent TOCTOU")
            rows.append(row)
            append_jsonl(out / "records.jsonl", row)
    grouped = []
    for condition in CONDITIONS:
        subset = [r for r in rows if r["condition"] == condition]
        unsafe = [r for r in subset if not r["safe_true"]]
        safe = [r for r in subset if r["safe_true"]]
        grouped.append(dict(condition=condition, states=len(subset), unsafe_probes=len(unsafe),
            unsafe_allow=sum(r["final_authorization"] == "ALLOW" for r in unsafe),
            safe_probes=len(safe), false_block=sum(r["final_authorization"] == "BLOCK" for r in safe),
            false_defer=sum(r["final_authorization"] == "DEFER" for r in safe)))
    write_json(out / "summary.json", dict(case_configurations=8, scene_clusters=4, actual_recorded_transitions=8,
        decision_rows=len(rows), grouped=grouped, new_Unity_calls=0, online_model_calls=0, candidate_actions_submitted=0,
        source_outcomes_already_known=True, scope="Dev offline stale-cache attribution on actual sequential native state transitions"))
    write_csv(out / "metrics.csv", grouped)
    finish_hashes(out)
    print("STALE TRACE COMPLETE:", len(rows), "decisions over 8 recorded native transitions:", out)


if __name__ == "__main__":
    main()
