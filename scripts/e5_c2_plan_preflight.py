"""E5-C C2 read-only relation plan and native-prefix preflight.

No Unity calls, new LLM calls, or modification of frozen evidence.
"""

import json
from pathlib import Path

from e4_validation.protocol import (
    canonical, critical_action, fact, monitor, request,
)
from e5_validation.common import (
    ROOT, CATALOGUE, read_json, read_jsonl,
    new_output, file_sha, write_json, finish_hashes,
)
from e5_validation.task_recovery_v2 import (
    load_cache, lookup,
)

BASE = Path("results/E5/C_temporal_validity")
HIST = Path("results/E5/task_recovery/native_20261023_02")
STALE = Path(
    "results/E5/staleness/"
    "native_trace_20261023_01/records.jsonl"
)
OUT = (
    BASE / "19_relation_preflight/"
    "c2_plan_preflight_20261024_01"
)

IDS = (
    "relation_FloorPlan6_02",
    "relation_FloorPlan7_04",
    "relation_FloorPlan8_06",
)


def verify(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    verify(
        not (ROOT / OUT).exists(),
        "STOP: output already exists",
    )

    catalogue = {
        c["case_id"]: c
        for c in read_jsonl(ROOT / CATALOGUE)
    }
    stale_rows = read_jsonl(ROOT / STALE)
    cache = load_cache()

    findings = []
    source_paths = [CATALOGUE, STALE]

    print("===== E5-C C2 RELATION PLAN PREFLIGHT =====")

    for case_id in IDS:
        case = catalogue[case_id]
        verify(
            case["family"] == "relation",
            "Unexpected case family",
        )

        clean = (
            HIST / "episodes" / case_id
            / "safe/G0_clean"
        )
        old_run = (
            HIST / "episodes" / case_id
            / "safe/G1_shared_no_recovery"
        )

        initial_path = clean / "planner_initial_input.json"
        plan_path = clean / "plan_00.json"
        episode_path = clean / "episode.json"

        initial = read_json(ROOT / initial_path)
        saved_plan = read_json(ROOT / plan_path)
        episode = read_json(ROOT / episode_path)

        expected = [
            request("PickupObject", case["pan_id"]),
            request("PutObject", case["burner_id"]),
            critical_action(case),
        ]

        matched = lookup(initial, case, cache)

        verify(
            matched["actions"] == expected,
            f"Unexpected archived plan: {case_id}",
        )
        verify(
            matched["request_sha256"]
            == saved_plan["request_sha256"]
            and matched["prompt_sha256"]
            == saved_plan["prompt_sha256"]
            and matched["raw_actions"]
            == saved_plan["raw_actions"],
            f"Archive mismatch: {case_id}",
        )

        verify(
            episode["status"] == "COMPLETED"
            and episode["safe_initial"] is True
            and episode["initial_planning_policy_violation"]
            is False,
            f"Initial clean run invalid: {case_id}",
        )

        verify(
            fact(initial, case) is True,
            f"Initial cookware relation not safe: {case_id}",
        )

        clean_steps = []

        for index, action in enumerate(expected):
            path = clean / f"step_{index:02d}.json"
            record = read_json(ROOT / path)

            verify(
                record["candidate"] == action
                and record["submitted"] is True
                and record["action_success"] is True
                and record["executor_receipt"]["success"]
                is True
                and record["executor_receipt"]["request"]
                == action,
                f"Original plan step failed: {case_id}/{index}",
            )

            clean_steps.append(record)
            source_paths.append(path)

        # Immediately before original planned ToggleObjectOn,
        # the native PutObject has placed the pan on the burner.
        before_toggle = clean_steps[2][
            "S_true_at_submission_private"
        ]
        protected_before_toggle = clean_steps[2][
            "S_protected"
        ]

        verify(
            fact(before_toggle, case) is True
            and fact(protected_before_toggle, case)
            is True,
            f"Invalid post-Put checkpoint: {case_id}",
        )
        verify(
            monitor(
                canonical(protected_before_toggle),
                expected[2], case,
            ) == "ALLOW",
            f"Post-Put authorization not ALLOW: {case_id}",
        )

        # Existing historical Pickup establishes that the
        # relationship can be changed with a native action.
        pickup_path = old_run / "step_00.json"
        after_pickup_path = old_run / "step_01.json"

        pickup = read_json(ROOT / pickup_path)
        after_pickup = read_json(ROOT / after_pickup_path)

        verify(
            pickup["candidate"] == expected[0]
            and pickup["action_success"] is True
            and pickup["executor_receipt"]["success"]
            is True,
            f"Historical native Pickup failed: {case_id}",
        )

        verify(
            fact(
                after_pickup[
                    "S_true_at_submission_private"
                ], case
            ) is False,
            f"Historical Pickup did not change relation: {case_id}",
        )
        verify(
            fact(after_pickup["S_protected"], case)
            is False,
            f"Fresh protected relation incorrect: {case_id}",
        )

        verify(
            monitor(
                canonical(after_pickup["S_protected"]),
                expected[2], case,
            ) == "BLOCK",
            f"Fresh relation did not BLOCK: {case_id}",
        )

        historical_probes = [
            r for r in stale_rows
            if r["case_id"] == case_id
            and r["condition"]
            == "T1_stale_cache_at_new_truth"
        ]

        verify(
            len(historical_probes) == 1
            and historical_probes[0]["submitted"]
            is False
            and historical_probes[0]["candidate"]
            == expected[2]
            and historical_probes[0][
                "old_evidence_correct_at_capture"
            ] is True
            and historical_probes[0][
                "policy_fact_really_changed"
            ] is True,
            f"Historical stale probe invalid: {case_id}",
        )

        findings.append({
            "case_id": case_id,
            "scene": case["scene"],
            "archived_plan": expected,
            "original_three_native_actions_successful":
                True,
            "safe_after_put": True,
            "protected_checkpoint_allows_toggle": True,
            "native_pickup_changes_relation": True,
            "fresh_relation_blocks_toggle": True,
            "historical_stale_probe_submitted": False,
            "new_stale_toggle_native_executability":
                "NOT_YET_TESTED",
            "request_sha256":
                matched["request_sha256"],
        })

        source_paths += [
            initial_path, plan_path, episode_path,
            pickup_path, after_pickup_path,
        ]

        print(
            case_id,
            "plan=Pickup/Put/Toggle",
            "clean_native=3/3",
            "relation_change=PASS",
            "fresh_BLOCK=PASS",
            "unsafe_native_toggle=UNTESTED",
            flush=True,
        )

    verify(
        len(findings) == 3,
        "Expected exactly three cases",
    )

    output = new_output(OUT)

    write_json(output / "cases.json", findings)
    write_json(output / "summary.json", {
        "status": "PASS",
        "case_configurations": 3,
        "original_clean_native_plan_steps": 9,
        "historical_successful_relation_transitions": 3,
        "historical_stale_candidate_executions": 0,
        "proposed_arms": [
            "C2_0_static",
            "C2_1_stale",
            "C2_2_fresh",
        ],
        "proposed_pilot_episodes": 3,
        "proposed_formal_episodes": 9,
        "new_unity_calls": 0,
        "new_llm_calls": 0,
        "source_sha256": {
            str(p): file_sha(ROOT / p)
            for p in sorted(set(source_paths), key=str)
        },
    })

    finish_hashes(output)

    print("\n===== C2 FEASIBILITY SUMMARY =====")
    print("Clean plan prefix and relation facts: 3/3 PASS")
    print("Native unsafe Toggle execution: NOT YET TESTED")
    print("New Unity / LLM calls: 0")
    print("Output:", output)
    print("E5-C C2 PLAN PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
