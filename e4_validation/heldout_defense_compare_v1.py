"""E4 Heldout-4: replay frozen LLM plans with existing defenses.

No new LLM calls. Original pairs.run_episode and Unity executor.
T0 only. Fresh recheck is a simulator-authoritative upper bound.
"""
import argparse
import collections
import hashlib
import json
import traceback
from pathlib import Path

from e4_validation import pairs
from e4_validation.consistency import (
    check_knob_burner,
    guarded_monitor,
)
from e4_validation.heldout_pairs_replay import preflight
from e4_validation.llm_shadow import build_prompt
from e4_validation.simulator import ROOT, start_controller

BASE = ROOT / "results/E4/07_heldout/heldout_unity_01"


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path):
    return [
        json.loads(x)
        for x in path.read_text().splitlines()
        if x.strip()
    ]


def identity(row):
    return (
        row["case_id"],
        row["safe_initial"],
        row["condition"],
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--defense",
        choices=("consistency", "fresh"),
        required=True,
    )
    p.add_argument("--case-id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    frozen = preflight()
    old_rows = read_jsonl(BASE / "records.jsonl")

    assert len(frozen) == len(old_rows) == 32
    assert all(r["status"] == "COMPLETED" for r in old_rows)

    baseline = {identity(r): r for r in old_rows}
    assert len(baseline) == 32

    trials = [
        x for x in frozen
        if not args.case_id
        or x[0]["case_id"] == args.case_id
    ]
    if not trials:
        p.error("Unknown case")

    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT):
        p.error("Output must be a new directory under project root")

    print(
        "PREFLIGHT PASS:",
        len(frozen), "frozen,",
        len(trials), "selected,",
        args.defense,
        flush=True,
    )

    if args.dry_run:
        return

    out.mkdir(parents=True, exist_ok=False)

    source_paths = [
        Path(__file__).resolve(),
        ROOT / "e4_validation/pairs.py",
        ROOT / "e4_validation/protocol.py",
        ROOT / "e4_validation/consistency.py",
        ROOT / "e4_validation/simulator.py",
        ROOT / "e4_validation/heldout_pairs_replay.py",
    ]

    pairs.write_json(out / "manifest.json", {
        "classification": "T0_researcher_adapted",
        "defense": args.defense,
        "oracle_query_used": args.defense == "fresh",
        "model_calls": 0,
        "total_frozen": 32,
        "selected": len(trials),
        "baseline_sha256": file_sha(BASE / "records.jsonl"),
        "source_hashes": {
            str(path.relative_to(ROOT)): file_sha(path)
            for path in source_paths
        },
    })

    controller = None
    rows = []

    try:
        controller = start_controller(trials[0][1]["scene"])

        for i, (job, case, actions, prompt) in enumerate(trials):
            frozen_condition = job["condition"]

            runtime_condition = (
                "protected_fresh_recheck"
                if args.defense == "fresh"
                and frozen_condition == "shared"
                else frozen_condition
            )

            folder = out / "episodes" / (
                f"{i:02d}_{job['case_id']}_"
                f"{'safe' if job['safe_initial'] else 'unsafe'}_"
                f"{frozen_condition}"
            )

            original = baseline[
                (job["case_id"], job["safe_initial"], frozen_condition)
            ]

            saved_plan = [
                dict(a, forceAction=False) for a in actions
            ]

            old_plan = pairs.plan
            old_monitor = pairs.monitor
            guard_calls = []

            def archived_plan(state_text, runtime_case):
                if runtime_case["case_id"] != case["case_id"]:
                    raise RuntimeError("CASE_ID_CHANGED")

                if build_prompt(
                    json.loads(state_text), runtime_case
                ) != prompt:
                    raise RuntimeError(
                        "FROZEN_PROMPT_RECREATION_MISMATCH"
                    )

                return {
                    "status": "PLAN" if saved_plan else "ABSTAIN",
                    "actions": saved_plan,
                    "planner": "archived_real_LLM",
                    "request_sha256": job["request_sha256"],
                }

            def filtered_monitor(state, action, runtime_case):
                if runtime_case["family"] != "attribute":
                    return old_monitor(state, action, runtime_case)

                check = check_knob_burner(state, runtime_case)
                verdict = guarded_monitor(
                    state, action, runtime_case, old_monitor
                )
                guard_calls.append({
                    "check": check,
                    "candidate": action,
                    "authorization": verdict,
                })
                return verdict

            try:
                pairs.plan = archived_plan

                if args.defense == "consistency":
                    pairs.monitor = filtered_monitor

                row = pairs.run_episode(
                    controller,
                    case,
                    job["safe_initial"],
                    runtime_condition,
                    folder,
                )

                if (
                    row["producer_clean_sha256"]
                    != original["producer_clean_sha256"]
                    or row["proposed_plan"]["actions"]
                    != original["proposed_plan"]["actions"]
                ):
                    raise RuntimeError(
                        "BASELINE_INITIAL_STATE_OR_PLAN_MISMATCH"
                    )

                row.update({
                    "condition": frozen_condition,
                    "runtime_condition": runtime_condition,
                    "defense": args.defense,
                    "paired_baseline_matched": True,
                    "llm_request_sha256": job["request_sha256"],
                    "oracle_query_used": args.defense == "fresh",
                    "guard_applicable": (
                        case["family"] == "attribute"
                        if args.defense == "consistency"
                        else None
                    ),
                })

                pairs.write_json(
                    folder / "guard_calls.json", guard_calls
                )
                pairs.write_json(
                    folder / "defended_episode.json", row
                )

            except Exception as exc:
                row = {
                    "case_id": job["case_id"],
                    "family": job["family"],
                    "scene": job["scene"],
                    "safe_initial": job["safe_initial"],
                    "condition": frozen_condition,
                    "defense": args.defense,
                    "status": "FAILED_OR_INCOMPLETE",
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                }
                pairs.write_json(folder / "failure.json", row)

            finally:
                pairs.plan = old_plan
                pairs.monitor = old_monitor

            rows.append(row)

            with (out / "records.jsonl").open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

            print(
                f"{i+1:02d}/{len(trials):02d}",
                job["case_id"],
                frozen_condition,
                job["safe_initial"],
                row["status"],
                "UAR=", row.get("unsafe_authorized"),
                "Violation=", row.get("violation_executed"),
                "Task=", row.get("task_success"),
                flush=True,
            )

    finally:
        if controller is not None:
            controller.stop()

        summary = {
            "defense": args.defense,
            "total": len(rows),
            "expected": len(trials),
            "status_counts": dict(collections.Counter(
                r["status"] for r in rows
            )),
            "unsafe_authorized": sum(
                bool(r.get("unsafe_authorized")) for r in rows
            ),
            "execution_violations": sum(
                bool(r.get("violation_executed")) for r in rows
            ),
            "task_success": sum(
                bool(r.get("task_success")) for r in rows
            ),
            "full_heldout": len(trials) == 32,
            "online_model_calls": 0,
            "oracle_query_used": args.defense == "fresh",
        }

        pairs.write_json(out / "summary.json", summary)
        print("SUMMARY:", summary, flush=True)

    if (
        len(rows) != len(trials)
        or any(r["status"] != "COMPLETED" for r in rows)
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
