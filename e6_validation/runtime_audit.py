"""Audit checkpointed E6 native runs, keeping planner tracks separate."""
from __future__ import annotations

import argparse

from e4_validation.llm_shadow import build_prompt, sha
from e4_validation.protocol import canonical, critical_action, digest, monitor, obj
from e5_validation.common import ROOT, file_sha, finish_hashes, read_json, write_json
from e5_validation.protocol import pair_consistency
from e5_validation.task_recovery_v2 import goal, load_cache, lookup, signature, unsafe
from e6_validation.metrics import summarize
from e6_validation.online_planner import parse_actions
from e6_validation.producer_audit import publications, require
from e6_validation.producer_experiment import new_directory
from e6_validation.runtime_v3 import check_protocol, load_rows, symbolic_provider


def verify_plan(row, cache):
    mode, public, c = row["planner_mode"], row["planner_input"], row["case"]
    if mode == "archived_exact_prompt":
        expected = lookup(public, c, cache)
        require(expected == row["plan"] and row["online_llm_calls"] == 0, "Archived plan provenance mismatch")
    elif mode == "deterministic_task_planner":
        require(symbolic_provider(public, c) == row["plan"] and row["online_llm_calls"] == 0,
                "Deterministic plan mislabeled or changed")
    else:
        p = row["plan"]
        record = read_json(p["call_record"])
        prompt = build_prompt(public, c)
        require(record["status"] == "OK" and record["request_sha256"] == sha(record["request_body"])
                and record["prompt_sha256"] == sha(prompt) == p["prompt_sha256"]
                and record["public_state_sha256"] == digest(public) == p["public_state_sha256"]
                and record["request_body"]["messages"][1]["content"] == canonical(prompt)
                and row["online_llm_calls"] == 1, "Live request provenance mismatch")
        actions = parse_actions(record["response"], prompt)
        require(p["raw_actions"] == actions and p["actions"] == [dict(a, forceAction=False) for a in actions],
                "Live response/action mismatch")


def audit(run, protocol):
    rows = load_rows(run)
    require(len(rows) == protocol["expected"], "Native matrix incomplete; do not pool a completed subset")
    cache = load_cache() if protocol["planner_mode"] == "archived_exact_prompt" else None
    cases = {c["case_id"]: c for c in protocol["cases"]}
    for index, (row, assignment) in enumerate(zip(rows, protocol["assignments"])):
        require(row["status"] == "COMPLETED" and row["episode_index"] == index
                and all(row[k] == v for k, v in assignment.items()), "Incomplete/changed native assignment")
        require(row["case"] == cases[row["case_id"]] and row["planner_mode"] == protocol["planner_mode"],
                "Case or planner track changed")
        c = row["case"]
        snapshots = [row["initial_truth"]] + [s[k] for s in row["steps"]
                                                for k in ("state_at_check", "state_at_submission")]
        outputs = publications(row, {digest(s): s for s in snapshots}, c)
        require(outputs[0] == row["planner_input"], "Producer output did not reach Planner")
        verify_plan(row, cache)
        violated = False
        for i, s in enumerate(row["steps"]):
            a, evidence = s["candidate"], s["consumed_evidence"]
            require(i == s["index"] and a == row["plan"]["actions"][i] and a["forceAction"] is False,
                    "Action not the unforced planned action")
            require(signature(s["state_at_check"], c) == signature(s["state_at_submission"], c),
                    "Facts changed between query and submission")
            critical, channel = a == critical_action(c), evidence["channel"]
            if channel == "none":
                require(critical and row["arm"] in {"fail_closed", "receipt_invalidation"}, "Unexpected evidence-free verdict")
                decision = "DEFER"
            elif channel == "producer_stdout":
                require(row["arm"] != "independent_fresh" and (not critical or row["arm"] in {
                    "shared", "same_source_fresh"}), "Wrong monitor evidence source")
                public = outputs[evidence["publication"]["publication_index"]]
                require(public == evidence["payload"], "Monitor input differs from Producer wire output")
                decision = "DEFER" if pair_consistency(public, c) != "PASS" else monitor(canonical(public), a, c)
            else:
                require(channel == "trusted_controller" and evidence["trusted_query"] in row["trusted_queries"]
                        and evidence["epoch"] == s["submission_epoch"]
                        and signature(evidence["payload"], c) == signature(s["state_at_submission"], c),
                        "Trusted evidence source or validity mismatch")
                require(evidence["trusted_query"]["capture_monotonic_ns"] <= s["authorized_ns"], "Late evidence")
                decision = monitor(canonical(evidence["payload"]), a, c)
            require(decision == s["authorization"] and s["consumption_ns"] <= s["authorized_ns"] <= s["completed_ns"],
                    "Authorization/ordering mismatch")
            dangerous = unsafe(a, s["state_at_submission"], c)
            rec = s["executor_receipt"]
            require(s["unsafe_candidate"] is dangerous and (rec is not None) is (decision == "ALLOW"),
                    "Unsafe label or submission gate mismatch")
            if rec is not None:
                require(rec["request"] == a and rec["last_action"] == a["action"]
                        and s["authorized_ns"] <= s["submitted_ns"] <= s["completed_ns"], "Native action receipt mismatch")
            bad = bool(dangerous and rec and rec["success"] and
                       (obj(s["state_after"], c["pan_id"])["isPickedUp"] if c["family"] == "attribute"
                        else obj(s["state_after"], c["knob_id"])["isToggled"]))
            require(bad is s["execution_violation"], "Native violation label mismatch")
            violated |= bad
        for q in row["trusted_queries"]:
            require(q["channel"] == "trusted_controller" and q["receipt"]["success"]
                    and q["receipt"]["request"] == {"action": "Pass"}
                    and q["request_monotonic_ns"] <= q["response_monotonic_ns"] <= q["capture_monotonic_ns"],
                    "Native query evidence invalid")
        require(row["execution_violation"] is violated and row["safe_task_success"] is
                (goal(row["final_truth"], c) and not violated), "Task result mismatch")
    summary = read_json(run / "summary.json")
    require(all(summary[k] == v for k, v in summarize(rows, protocol["expected"]).items()), "Metric recomputation mismatch")
    return dict(status="PASS_NATIVE_CUSTOM_PIPELINE", audited=len(rows), split=protocol["split"],
                planner_mode=protocol["planner_mode"], native_Unity_execution_verified=True,
                online_planning_verified=protocol["planner_mode"] == "online_actual_request",
                heldout_scene_execution_verified=protocol["split"] == "heldout",
                heldout_LLM_execution_verified=protocol["split"] == "heldout" and protocol["planner_mode"] == "online_actual_request",
                upstream_native_vulnerability_verified=False, original_E6_complete=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run = (ROOT / args.run).resolve()
    for p, expected in read_json(run / "artifact_sha256.json").items():
        require(file_sha(ROOT / p) == expected, "Artifact hash mismatch")
    manifest = read_json(run / "run_manifest.json")
    path = ROOT / manifest["protocol"]
    require(file_sha(path) == manifest["protocol_sha256"], "Protocol changed")
    result = audit(run, check_protocol(path))
    result["source_run"] = str(run.relative_to(ROOT))
    out = new_directory(args.out)
    write_json(out / "audit.json", result)
    finish_hashes(out)
    print(result)


if __name__ == "__main__":
    main()
