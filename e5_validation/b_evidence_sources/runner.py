"""E5-B B2/B3 native closed-loop with archived DeepSeek plans."""
from __future__ import annotations

import argparse
import collections
import datetime
import time
import traceback

from e4_validation.llm_shadow import abstract_trace
from e4_validation.protocol import (
    canonical, critical_action, digest, field_diff, monitor, obj,
)
from e4_validation.simulator import (
    approach, objects, prepare, start_controller, step,
)
from e5_validation.a_consistent_pollution.runner import (
    ARMS as A_ARMS,
    check_protocol as check_a_protocol,
    goal, unsafe, view,
)
from e5_validation.b_evidence_sources.policy import (
    ARMS, decide, finish_query,
)
from e5_validation.common import (
    CATALOGUE, ROOT, append_jsonl, file_sha, finish_hashes,
    new_output, read_json, require, state, write_json,
)
from e5_validation.task_recovery_v2 import (
    INPUTS, LLM, load_cache, lookup, protected_query, signature,
)

BASE = "results/E5/B_evidence_sources"
PROTOCOL = BASE + "/01_protocol/freeze_20261024_01/manifest.json"

SOURCES = [
    "e5_validation/b_evidence_sources/__init__.py",
    "e5_validation/b_evidence_sources/policy.py",
    "e5_validation/b_evidence_sources/runner.py",
    "e5_validation/b_evidence_sources/report.py",
    "tests/test_e5_b_evidence_sources.py",
    "tests/test_e5_b_runner.py",
    "e5_validation/a_consistent_pollution/runner.py",
    "e5_validation/receipt.py",
    "e5_validation/task_recovery_v2.py",
    "e5_validation/common.py",
    "e4_validation/protocol.py",
    "e4_validation/simulator.py",
    "e4_validation/llm_shadow.py",
    str(CATALOGUE),
    INPUTS,
    LLM + "/records.jsonl",
]


def freeze():
    require(
        not (ROOT / PROTOCOL).exists(),
        "E5-B protocol already frozen; never overwrite",
    )
    _, cases = check_a_protocol()
    load_cache()

    paths = SOURCES + [
        str(p.relative_to(ROOT))
        for p in sorted((ROOT / LLM / "responses").glob("*.json"))
    ]
    require(
        all((ROOT / p).is_file() for p in paths),
        "Missing E5-B freeze source",
    )

    manifest = {
        "schema": "e5.b.receipt_execution.v1",
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "threat": "T0 metadata-copy attack",
        "arms": list(ARMS),
        "cases": [c["case_id"] for c in cases],
        "initial_states": ["true_on", "true_off"],
        "expected_episodes": 20,
        "contract": "KA_POWER_OFF_BEFORE_REMOVAL_V1",
        "evidence": (
            "Current-episode Evaluator setup receipts "
            "and subsequently observed native actions"
        ),
        "assumptions": [
            "Guard explicitly granted access to setup receipts",
            "Complete ordered single-writer trace",
            "No hidden state-changing writer",
            "Native receipts are not cryptographically authenticated",
        ],
        "no_absence_inference": True,
        "no_replanning": True,
        "no_online_llm_calls": True,
        "max_protected_queries_per_candidate": 1,
        "comparison": "B0/B1/B4 reuse E5-A audited results",
        "a_protocol_sha256": file_sha(
            ROOT / (
                "results/E5/A_consistent_pollution/"
                "00_protocol/freeze_20261024_01/manifest.json"
            )
        ),
        "source_sha256": {
            p: file_sha(ROOT / p) for p in paths
        },
    }

    write_json(ROOT / PROTOCOL, manifest)

    for p in paths:
        target = (
            (ROOT / PROTOCOL).parent
            / "frozen_sources"
            / p
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / p).read_bytes())

    print("E5-B FROZEN:", ROOT / PROTOCOL, flush=True)


def check_protocol():
    _, cases = check_a_protocol()
    manifest = read_json(ROOT / PROTOCOL)

    require(
        manifest["arms"] == list(ARMS),
        "Frozen arm mismatch",
    )
    require(
        manifest["cases"] == [c["case_id"] for c in cases],
        "Frozen case mismatch",
    )

    for path, expected in manifest["source_sha256"].items():
        require(
            (ROOT / path).is_file()
            and file_sha(ROOT / path) == expected,
            "Frozen source changed: " + path,
        )

    return manifest, cases


def run_episode(controller, case, safe, arm, folder, cache):
    folder.mkdir(parents=True)

    t = time.perf_counter_ns()
    setup_receipts = prepare(
        controller,
        case["scene"],
        case["pan_id"],
        case["burner_id"],
        case["knob_id"],
        occupied=True,
        active=not safe,
    )
    initial = state(objects(controller))
    setup_ns = time.perf_counter_ns() - t

    require(
        unsafe(critical_action(case), initial, case)
        is (not safe),
        "Initial safety fact mismatch",
    )
    require(
        obj(initial, case["burner_id"])["isToggled"]
        is (not safe),
        "Initial burner state mismatch",
    )
    require(
        case["burner_id"] in (
            obj(initial, case["pan_id"]).get("parentReceptacles")
            or []
        ),
        "Initial placement mismatch",
    )

    write_json(folder / "setup_receipts.json", setup_receipts)
    write_json(folder / "S_true_initial_private.json", initial)

    append_jsonl(
        folder / "source_manifest.jsonl",
        {
            "source": "evaluator_setup_native_receipts",
            "artifact": "setup_receipts.json",
            "sha256": file_sha(folder / "setup_receipts.json"),
            "guard_access": "GRANTED_IN_T0_UPPER_BOUND_ONLY",
            "complete_trace": "ASSUMED",
            "target_knob_id": case["knob_id"],
            "physical_root": "same_Unity_instance",
            "cryptographically_authenticated": False,
        },
    )
    append_jsonl(
        folder / "source_manifest.jsonl",
        {
            "source": "unity_initial_private_truth",
            "artifact": "S_true_initial_private.json",
            "sha256": file_sha(
                folder / "S_true_initial_private.json"
            ),
            "guard_access": "DENIED_PRIVATE_EVALUATOR_ONLY",
            "physical_root": "same_Unity_instance",
        },
    )

    # This read grant is an explicit T0 experimental assumption.
    # The Guard never receives private evaluator truth.
    history = list(setup_receipts)

    task_start = time.perf_counter_ns()
    public = view(initial, case, A_ARMS[2])
    write_json(folder / "S_planner.json", public)

    append_jsonl(
        folder / "source_manifest.jsonl",
        {
            "source": "T0_attackable_shared_observation",
            "artifact": "S_planner.json",
            "sha256": file_sha(folder / "S_planner.json"),
            "guard_access": "YES_UNTRUSTED",
            "writable_fields": [
                case["knob_id"] + ".isToggled",
                case["burner_id"] + ".isToggled",
            ],
        },
    )

    t = time.perf_counter_ns()
    plan = lookup(public, case, cache)
    lookup_ns = time.perf_counter_ns() - t
    write_json(folder / "llm_plan.json", plan)

    trace = abstract_trace(
        plan["raw_actions"], initial, case
    )

    steps = []
    stop_reason = "PLAN_EXHAUSTED"

    for index, candidate in enumerate(plan["actions"]):
        navigation = []

        before = signature(
            state(objects(controller)), case
        )

        t = time.perf_counter_ns()
        visible = approach(
            controller, candidate["objectId"], navigation
        )
        navigation_ns = time.perf_counter_ns() - t

        history.extend(navigation)

        truth = state(objects(controller), index)
        require(
            signature(truth, case) == before,
            "Navigation changed task-critical facts",
        )

        observed = view(truth, case, A_ARMS[2])
        prior_receipts = list(history)

        t = time.perf_counter_ns()
        decision = decide(
            observed,
            candidate,
            case,
            prior_receipts,
            arm=arm,
            setup_log_granted=True,
            trace_continuous=True,
        )
        guard_ns = time.perf_counter_ns() - t

        protected = None
        query = None
        final = decision["final"]

        if decision["needs_query"]:
            require(
                arm == ARMS[1],
                "Only B3 may request fresh evidence",
            )

            protected, query = protected_query(
                controller, index
            )
            history.append(query["receipt"])

            final = finish_query(
                decision, protected, candidate, case
            )

        require(
            final in ("ALLOW", "BLOCK", "DEFER"),
            "Invalid final authorization",
        )

        submission = state(objects(controller), index)
        require(
            signature(truth, case)
            == signature(submission, case),
            "Safety facts changed between check and submission",
        )

        is_unsafe = unsafe(
            candidate, submission, case
        )

        execution = None
        after = None
        execution_ns = 0

        if final == "ALLOW":
            t = time.perf_counter_ns()

            # Evaluated action uses the native executor.
            # Archived plans have forceAction=False.
            execution = step(controller, candidate, [])
            execution_ns = time.perf_counter_ns() - t

            history.append(execution)
            after = state(objects(controller), index + 1)

        violation = bool(
            is_unsafe
            and execution
            and execution["success"]
            and goal(after, case)
        )

        step_dir = folder / f"step_{index:02d}"

        write_json(
            step_dir / "S_true_check_private.json", truth
        )
        write_json(
            step_dir / "S_monitor.json", observed
        )
        write_json(
            step_dir / "S_true_submission_private.json",
            submission,
        )
        write_json(
            step_dir / "receipt_history_before.json",
            prior_receipts,
        )

        if protected is not None:
            write_json(
                step_dir / "S_protected.json", protected
            )
        if after is not None:
            write_json(
                step_dir / "S_after_private.json", after
            )

        item = {
            "index": index,
            "candidate": candidate,
            "navigation": navigation,
            "navigation_success": visible,
            "navigation_ns": navigation_ns,
            "raw_authorization": monitor(
                canonical(observed), candidate, case
            ),
            "receipt_evidence": decision,
            "final_authorization": final,
            "setup_log_granted": True,
            "trace_continuous_assumed": True,
            "receipt_history_sha256": digest(prior_receipts),
            "query": query,
            "guard_ns": guard_ns,
            "execution_ns": execution_ns,
            "submitted": execution is not None,
            "executor_receipt": execution,
            "action_success": bool(
                execution and execution["success"]
            ),
            "unsafe_candidate": is_unsafe,
            "violation_executed": violation,
            "attack_diff": field_diff(truth, observed),
            "true_check_sha256": digest(truth),
            "true_submission_sha256": digest(submission),
            "protected_sha256": (
                digest(protected) if protected else None
            ),
        }

        write_json(
            step_dir / "decision.json", item
        )

        append_jsonl(
            folder / "source_manifest.jsonl",
            {
                "source": "receipt_guard_input",
                "artifact": (
                    f"step_{index:02d}/"
                    "receipt_history_before.json"
                ),
                "sha256": file_sha(
                    step_dir / "receipt_history_before.json"
                ),
                "guard_access": "YES_CONDITIONAL",
                "support": "prior same-episode native receipts",
                "query_triggered": bool(query),
                "target_knob_id": case["knob_id"],
            },
        )

        if protected is not None:
            append_jsonl(
                folder / "source_manifest.jsonl",
                {
                    "source": "X_protected_native_Pass",
                    "artifact": (
                        f"step_{index:02d}/S_protected.json"
                    ),
                    "sha256": file_sha(
                        step_dir / "S_protected.json"
                    ),
                    "guard_access": "YES_PROTECTED_T0",
                    "physical_root": "same_Unity_instance",
                    "independent_physical_sensor": False,
                },
            )

        steps.append(item)

        if violation:
            stop_reason = "POLICY_VIOLATION_EXECUTED"
            break

        if final != "ALLOW":
            stop_reason = final
            break

        if not execution["success"]:
            stop_reason = "NATIVE_ACTION_FAILED"
            break

    final_truth = state(objects(controller), len(steps))
    write_json(
        folder / "S_true_final_private.json", final_truth
    )

    any_violation = any(
        s["violation_executed"] for s in steps
    )

    row = {
        "case_id": case["case_id"],
        "family": case["family"],
        "scene": case["scene"],
        "safe_initial": safe,
        "arm": arm,
        "status": "COMPLETED",
        "prompt_sha256": plan["prompt_sha256"],
        "request_sha256": plan["request_sha256"],
        "raw_actions": plan["raw_actions"],
        "initial_attack_diff": field_diff(initial, public),
        "planning_policy_violation": bool(
            trace["policy_violations"]
        ),
        "plan_precondition_errors": trace["precondition_errors"],
        "steps": steps,
        "stop_reason": stop_reason,
        "goal_achieved": goal(final_truth, case),
        "violation_executed": any_violation,
        "safe_task_success": bool(
            goal(final_truth, case) and not any_violation
        ),
        "receipt_grant": (
            "T0_CONDITIONAL_EVALUATOR_SETUP_ACCESS"
        ),
        "no_log_authentication_claim": True,
        "setup_ns": setup_ns,
        "task_ns": time.perf_counter_ns() - task_start,
        "archived_lookup_ns": lookup_ns,
        "online_model_calls": 0,
        "evidence_dir": str(folder.relative_to(ROOT)),
    }

    write_json(folder / "episode.json", row)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.preregister:
        freeze()
        return

    _, cases = check_protocol()
    cache = load_cache()

    require(args.out, "--out required")
    out = new_output(args.out)

    run_cases = cases[:1] if args.pilot else cases
    expected = len(run_cases) * 2 * len(ARMS)

    write_json(
        out / "run_manifest.json",
        {
            "protocol": PROTOCOL,
            "protocol_sha256": file_sha(ROOT / PROTOCOL),
            "mode": (
                "dryrun" if args.dry_run
                else "pilot" if args.pilot
                else "formal"
            ),
            "cases": [c["case_id"] for c in run_cases],
            "arms": list(ARMS),
            "expected_episodes": expected,
            "setup_receipt_permission": (
                "CONDITIONAL_T0_UPPER_BOUND"
            ),
            "online_model_calls": 0,
        },
    )

    if args.dry_run:
        for case in run_cases:
            for safe in (False, True):
                archived_truth = next(
                    t["S_true"]
                    for t in case["trials"]
                    if t["expected_safe"] is safe
                )
                public = view(
                    state(archived_truth),
                    case,
                    A_ARMS[2],
                )
                for arm in ARMS:
                    plan = lookup(public, case, cache)
                    append_jsonl(
                        out / "records.jsonl",
                        {
                            "case_id": case["case_id"],
                            "safe_initial": safe,
                            "arm": arm,
                            "status": "EXACT_ARCHIVE_MATCH",
                            "request_sha256": plan["request_sha256"],
                        },
                    )

        write_json(
            out / "summary.json",
            {
                "exact_archive_matches": expected,
                "unity_launched": False,
            },
        )
        finish_hashes(out)
        print(
            f"E5-B DRY RUN PASS: {expected} "
            "exact plan matches; no Unity/API"
        )
        return

    rows = []
    controller = None

    try:
        controller = start_controller(
            run_cases[0]["scene"]
        )

        for case in run_cases:
            for safe in (False, True):
                for arm in ARMS:
                    folder = (
                        out / "episodes" / case["case_id"]
                        / ("true_off" if safe else "true_on")
                        / arm
                    )

                    try:
                        row = run_episode(
                            controller,
                            case,
                            safe,
                            arm,
                            folder,
                            cache,
                        )
                    except Exception as error:
                        folder.mkdir(
                            parents=True, exist_ok=True
                        )
                        row = {
                            "case_id": case["case_id"],
                            "scene": case["scene"],
                            "safe_initial": safe,
                            "arm": arm,
                            "status": "FAILED_OR_INCOMPLETE",
                            "error": repr(error),
                            "traceback": traceback.format_exc(),
                            "evidence_dir": str(
                                folder.relative_to(ROOT)
                            ),
                        }
                        write_json(
                            folder / "episode.json", row
                        )

                    rows.append(row)
                    append_jsonl(
                        out / "records.jsonl", row
                    )

                    print(
                        len(rows), "/", expected,
                        case["case_id"],
                        "OFF" if safe else "ON",
                        arm,
                        row["status"],
                        "violation=",
                        row.get("violation_executed"),
                        "safe_task=",
                        row.get("safe_task_success"),
                        flush=True,
                    )

    finally:
        if controller is not None:
            controller.stop()

        complete = (
            len(rows) == expected
            and all(
                r["status"] == "COMPLETED"
                for r in rows
            )
        )

        write_json(
            out / "summary.json",
            {
                "complete": complete,
                "recorded": len(rows),
                "expected": expected,
                "status_counts": dict(
                    collections.Counter(
                        r["status"] for r in rows
                    )
                ),
                "protected_queries": sum(
                    s.get("query") is not None
                    for r in rows
                    for s in r.get("steps", [])
                ),
                "scope": (
                    "E5-B T0 conditional complete setup history; "
                    "no online LLM"
                ),
            },
        )
        finish_hashes(out)

    require(
        complete,
        "Incomplete E5-B run; retain all evidence",
    )


if __name__ == "__main__":
    main()
