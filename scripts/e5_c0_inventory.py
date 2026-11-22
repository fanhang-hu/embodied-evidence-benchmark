"""E5-C C0: read-only evidence inventory and OFF-plan feasibility.

Reads frozen E5 records. Writes only a new derived report.
Does not launch Unity, change experiments, or call the LLM.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

from e4_validation.protocol import critical_action, obj
from e5_validation.a_consistent_pollution.runner import selected_cases
from e5_validation.task_recovery_v2 import load_cache, lookup

ROOT = Path.cwd()

E5 = Path("results/E5")
A = E5 / "A_consistent_pollution"
B = E5 / "B_evidence_sources"

STALE = E5 / "staleness/native_trace_20261023_01"
BINDING = E5 / "binding/native_20261023_02"
RECOVERY = E5 / "02_summary/task_recovery_20261023_02"

A_RUN = A / "02_native/run_20261024_01"
A_AUDIT = A / "03_report/audit_20261024_02"

B_RUN = B / "05_native/run_20261024_01"
B_AUDIT = B / "06_report/audit_20261024_01"

OUT = E5 / "C_temporal_validity/00_inventory/inventory_20261024_01"


def load(relative):
    path = ROOT / relative
    assert path.is_file(), f"MISSING: {relative}"
    return json.loads(path.read_text())


def load_lines(relative):
    path = ROOT / relative
    assert path.is_file(), f"MISSING: {relative}"
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def sha(relative):
    h = hashlib.sha256()
    with (ROOT / relative).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    assert not (ROOT / OUT).exists(), (
        f"STOP: output already exists: {OUT}"
    )

    sources = [
        STALE / "summary.json",
        STALE / "records.jsonl",
        BINDING / "summary.json",
        BINDING / "records.jsonl",
        RECOVERY / "audit.json",
        A_RUN / "records.jsonl",
        A_AUDIT / "summary.json",
        B_RUN / "records.jsonl",
        B_AUDIT / "summary.json",
    ]

    print("===== C0-1: HISTORICAL EVIDENCE =====")

    stale_summary = load(STALE / "summary.json")
    stale_rows = load_lines(STALE / "records.jsonl")

    assert stale_summary["actual_recorded_transitions"] == 8
    assert stale_summary["decision_rows"] == 40
    assert len(stale_rows) == 40
    assert stale_summary["candidate_actions_submitted"] == 0

    transitions = [
        r for r in stale_rows
        if r["condition"] == "T1_stale_cache_at_new_truth"
    ]
    assert len(transitions) == 8
    assert len(set(r["case_id"] for r in transitions)) == 8

    # Independently verify that each historical transition
    # was actually submitted and succeeded in native Unity.
    transition_evidence = []

    for r in transitions:
        old_step = Path(r["old_step"])
        next_step = Path(r["new_step"])

        old = load(old_step)
        load(next_step)

        receipt = old["executor_receipt"]

        assert old["submitted"] is True
        assert old["action_success"] is True
        assert receipt is not None
        assert receipt["success"] is True
        assert receipt["request"] == r["actual_transition_action"]
        assert receipt["request"]["forceAction"] is False
        assert r["old_evidence_correct_at_capture"] is True
        assert r["policy_fact_really_changed"] is True

        transition_evidence.append({
            "case_id": r["case_id"],
            "family": r["family"],
            "native_action": r["actual_transition_action"],
            "old_step": str(old_step),
            "new_step": str(next_step),
            "source": "E5 prior sequential native transition",
        })

        sources.extend([old_step, next_step])

    print("Historical transitions:", len(transition_evidence))
    print(
        "Transition families:",
        dict(Counter(x["family"] for x in transition_evidence))
    )
    print("Offline decisions:", len(stale_rows))

    for group in stale_summary["grouped"]:
        print(
            group["condition"],
            "unsafe_allow=", group["unsafe_allow"],
            "false_block=", group["false_block"],
            "false_defer=", group["false_defer"],
        )

    binding_summary = load(BINDING / "summary.json")
    binding_rows = load_lines(BINDING / "records.jsonl")

    assert binding_summary["complete"] is True
    assert binding_summary["physical_controls"] == 9
    assert binding_summary["decisions"] == 54
    assert len(binding_rows) == 54
    assert binding_summary["candidate_actions_submitted"] == 0

    print("Existing binding controls:", 9)
    print("Existing binding judgments:", len(binding_rows))

    recovery_audit = load(RECOVERY / "audit.json")
    assert recovery_audit["status"] == "PASS"
    assert recovery_audit["episodes"] == 80
    print("Existing recovery episodes:", 80)

    a_audit = load(A_AUDIT / "summary.json")
    b_audit = load(B_AUDIT / "summary.json")

    assert a_audit["audited_episodes"] == 50
    assert b_audit["audited"] == 20
    assert a_audit["source_sha256"] == sha(A_RUN / "records.jsonl")
    assert b_audit["source_sha256"] == sha(B_RUN / "records.jsonl")

    print("E5-A audited:", 50)
    print("E5-B audited:", 20)

    print("\n===== C0-2: FROZEN CLEAN-OFF PLANS =====")

    cases = selected_cases()
    cache = load_cache()
    assert len(cases) == 5

    plans = []

    for case in cases:
        case_id = case["case_id"]

        folder = (
            A_RUN / "episodes" / case_id
            / "true_off" / "A0_clean"
        )

        initial = load(folder / "S_true_initial_private.json")
        public = load(folder / "S_planner.json")
        archived = load(folder / "llm_plan.json")

        assert obj(initial, case["knob_id"])["isToggled"] is False
        assert obj(initial, case["burner_id"])["isToggled"] is False
        assert obj(initial, case["pan_id"])["isPickedUp"] is False
        assert case["burner_id"] in (
            obj(initial, case["pan_id"]).get("parentReceptacles") or []
        )

        # Clean public state is not poisoned.
        assert public == initial

        # Strict archived real-LLM prompt match; no API call.
        matched = lookup(public, case, cache)

        assert matched["prompt_sha256"] == archived["prompt_sha256"]
        assert matched["request_sha256"] == archived["request_sha256"]
        assert matched["raw_actions"] == archived["raw_actions"]

        actions = matched["actions"]
        critical = critical_action(case)

        contains_pickup = critical in actions
        first_is_pickup = bool(actions) and actions[0] == critical

        row = {
            "case_id": case_id,
            "scene": case["scene"],
            "prompt_sha256": matched["prompt_sha256"],
            "request_sha256": matched["request_sha256"],
            "actions": actions,
            "contains_critical_pickup": contains_pickup,
            "first_action_critical_pickup": first_is_pickup,
            "source": str(folder),
        }
        plans.append(row)

        sources.extend([
            folder / "S_true_initial_private.json",
            folder / "S_planner.json",
            folder / "llm_plan.json",
        ])

        print(
            case_id,
            "actions=", len(actions),
            "pickup_present=", contains_pickup,
            "pickup_first=", first_is_pickup,
        )

    # Do not silently choose only cases with favorable plans.
    all_pickup = all(p["contains_critical_pickup"] for p in plans)

    summary = {
        "schema": "e5.c.c0.inventory.v1",
        "scope": "E5 development reuse of previously seen cases",
        "historical_transitions": 8,
        "historical_offline_decisions": 40,
        "historical_binding_controls": 9,
        "historical_binding_decisions": 54,
        "historical_recovery_episodes": 80,
        "e5_a_audited_episodes": 50,
        "e5_b_audited_episodes": 20,
        "c1_candidate_configurations": 5,
        "c1_plans_with_critical_pickup": sum(
            p["contains_critical_pickup"] for p in plans
        ),
        "c1_all_plans_contain_pickup": all_pickup,
        "c1_design": {
            "groups": ["C1_0_static", "C1_1_stale", "C1_2_fresh"],
            "planned_episodes": 15,
            "capture_true_state": "OFF",
            "transition": "native OFF-to-ON only for stale/fresh",
            "plan": "identical archived real-LLM OFF plan",
            "claim": "sequential evidence expiration, not TOCTOU",
        },
        "sources_sha256": {
            str(p): sha(p) for p in sorted(set(sources), key=str)
        },
    }

    target = ROOT / OUT
    target.mkdir(parents=True)

    (target / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    (target / "plans.json").write_text(
        json.dumps(plans, indent=2, ensure_ascii=False) + "\n"
    )
    (target / "transitions.json").write_text(
        json.dumps(
            transition_evidence, indent=2, ensure_ascii=False
        ) + "\n"
    )

    print("\n===== E5-C C0 SUMMARY =====")
    print("Prior evidence verification: PASS")
    print(
        "OFF plans containing target pickup:",
        summary["c1_plans_with_critical_pickup"], "/5"
    )
    print("No new Unity/API calls")
    print("Output:", target)

    if not all_pickup:
        raise SystemExit(
            "C0 COMPLETED WITH PLAN-COVERAGE LIMITATION; "
            "review all five plans before C1."
        )

    print("E5-C C0 INVENTORY: PASS")


if __name__ == "__main__":
    main()
