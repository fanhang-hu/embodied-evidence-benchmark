"""E5-C C1 formal paired native execution; reuse frozen Pilot logic."""
from __future__ import annotations

import argparse
import collections
import datetime
import traceback

from e4_validation.protocol import critical_action
from e4_validation.simulator import start_controller
from e5_validation.c_temporal.c1_pilot import (
    ARMS, check as pilot_check, run_episode,
)
from e5_validation.common import (
    ROOT, append_jsonl, file_sha, finish_hashes, new_output,
    read_json, require, write_json,
)
from e5_validation.task_recovery_v2 import load_cache, lookup

BASE = "results/E5/C_temporal_validity"
PILOT_FREEZE = (
    BASE + "/01_protocol/c1_pilot_freeze_20261024_01/manifest.json"
)
FORMAL_FREEZE = (
    BASE + "/05_protocol/c1_formal_freeze_20261024_01/manifest.json"
)
A_CLEAN = (
    "results/E5/A_consistent_pollution/"
    "02_native/run_20261024_01"
)

SOURCES = (
    "e5_validation/c_temporal/c1_pilot.py",
    "e5_validation/c_temporal/c1_audit.py",
    "e5_validation/c_temporal/c1_formal.py",
    "e5_validation/c_temporal/c1_formal_audit.py",
    "e5_validation/common.py",
    "e5_validation/task_recovery_v2.py",
    "e5_validation/a_consistent_pollution/runner.py",
    "e4_validation/protocol.py",
    "e4_validation/simulator.py",
    PILOT_FREEZE,
    BASE + "/00_inventory/inventory_20261024_01/summary.json",
)


def exact_off_plan(case, cache):
    source = (
        ROOT / A_CLEAN / "episodes" / case["case_id"]
        / "true_off" / "A0_clean"
    )
    public = read_json(source / "S_planner.json")
    plan = lookup(public, case, cache)

    require(
        plan["actions"] == [critical_action(case)],
        "Non-one-step OFF plan",
    )

    original = read_json(source / "llm_plan.json")

    require(
        (
            plan["request_sha256"],
            plan["prompt_sha256"],
            plan["raw_actions"],
        ) == (
            original["request_sha256"],
            original["prompt_sha256"],
            original["raw_actions"],
        ),
        "Archived OFF plan mismatch",
    )
    return plan


def freeze():
    require(
        not (ROOT / FORMAL_FREEZE).exists(),
        "Formal protocol already frozen",
    )

    cases = pilot_check()
    cache = load_cache()

    plans = {
        c["case_id"]: exact_off_plan(
            c, cache
        )["request_sha256"]
        for c in cases
    }

    hashes = {
        path: file_sha(ROOT / path)
        for path in SOURCES
    }

    write_json(ROOT / FORMAL_FREEZE, {
        "schema": "e5.c.c1.native_formal.v1",
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "case_ids": [c["case_id"] for c in cases],
        "arms": list(ARMS),
        "episodes": 15,
        "pilot": (
            "Prior three-episode development run; "
            "excluded from formal results"
        ),
        "plan_sha256_by_case": plans,
        "source_sha256": hashes,
        "native_change": (
            "Nonforced OFF-to-ON after frozen plan "
            "and before authorization"
        ),
        "old_capture": "Native Pass; unchanged snapshot",
        "fresh_capture": (
            "Additional protected native Pass before authorization"
        ),
        "scope": (
            "Sequential controlled state change; "
            "not concurrent TOCTOU or native T1 attack"
        ),
        "no_new_LLM": True,
        "no_replanning": True,
        "no_artificial_sleep": True,
    })

    print(
        "E5-C C1 FORMAL PROTOCOL FROZEN:",
        ROOT / FORMAL_FREEZE,
    )


def check():
    cases = pilot_check()
    frozen = read_json(ROOT / FORMAL_FREEZE)

    require(
        frozen["case_ids"]
        == [c["case_id"] for c in cases],
        "Case set changed",
    )
    require(
        frozen["arms"] == list(ARMS)
        and frozen["episodes"] == 15,
        "Arm/count changed",
    )

    for source, expected in frozen["source_sha256"].items():
        require(
            (ROOT / source).is_file()
            and file_sha(ROOT / source) == expected,
            "Formal source changed: " + source,
        )

    cache = load_cache()

    for case in cases:
        require(
            exact_off_plan(
                case, cache
            )["request_sha256"]
            == frozen["plan_sha256_by_case"][
                case["case_id"]
            ],
            "OFF archive changed",
        )

    return cases, cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregister", action="store_true"
    )
    parser.add_argument(
        "--dry-run", action="store_true"
    )
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.preregister:
        freeze()
        return

    require(args.out, "--out required")
    cases, cache = check()
    out = new_output(args.out)

    write_json(out / "run_manifest.json", {
        "protocol": FORMAL_FREEZE,
        "protocol_sha256": file_sha(
            ROOT / FORMAL_FREEZE
        ),
        "cases": [c["case_id"] for c in cases],
        "arms": list(ARMS),
        "expected_episodes": 15,
        "mode": (
            "dryrun" if args.dry_run
            else "formal_native"
        ),
        "pilot_excluded": True,
        "online_llm_calls": 0,
    })

    if args.dry_run:
        for case in cases:
            plan = exact_off_plan(case, cache)

            for arm in ARMS:
                append_jsonl(
                    out / "records.jsonl",
                    {
                        "case_id": case["case_id"],
                        "arm": arm,
                        "request_sha256": plan[
                            "request_sha256"
                        ],
                        "status": "EXACT_ARCHIVED_OFF_PLAN",
                    },
                )

        write_json(out / "summary.json", {
            "matches": 15,
            "unity_calls": 0,
        })
        finish_hashes(out)

        print(
            "E5-C C1 FORMAL DRY RUN PASS: "
            "15 exact plan matches; no Unity/API"
        )
        return

    controller = None
    rows = []

    try:
        controller = start_controller(
            cases[0]["scene"]
        )

        for case in cases:
            for arm in ARMS:
                folder = (
                    out / "episodes"
                    / case["case_id"] / arm
                )

                try:
                    row = run_episode(
                        controller,
                        case,
                        arm,
                        folder,
                        cache,
                    )

                except Exception as exc:
                    folder.mkdir(
                        parents=True, exist_ok=True
                    )
                    row = {
                        "case_id": case["case_id"],
                        "arm": arm,
                        "status": "FAILED_OR_INCOMPLETE",
                        "error": repr(exc),
                        "traceback": traceback.format_exc(),
                        "evidence_dir": str(
                            folder.relative_to(ROOT)
                        ),
                    }
                    write_json(
                        folder / "failure.json", row
                    )

                append_jsonl(
                    out / "records.jsonl", row
                )
                rows.append(row)

                print(
                    f"{len(rows)}/15 "
                    f"{case['case_id']} {arm} "
                    f"{row['status']} "
                    f"auth={row.get('final_authorization')} "
                    f"UAR={bool(row.get('unsafe_at_authorization') and row.get('final_authorization') == 'ALLOW')} "
                    f"violation={row.get('execution_violation')} "
                    f"safe_task={row.get('safe_task_success')}",
                    flush=True,
                )

    finally:
        if controller is not None:
            controller.stop()

        complete = (
            len(rows) == 15
            and all(
                r["status"] == "COMPLETED"
                for r in rows
            )
        )

        write_json(out / "summary.json", {
            "expected": 15,
            "recorded": len(rows),
            "complete": complete,
            "status_counts": dict(
                collections.Counter(
                    r["status"] for r in rows
                )
            ),
            "capture_passes": sum(
                r.get("capture_pass_count", 0)
                for r in rows
            ),
            "additional_fresh_passes": sum(
                r.get("query_count", 0)
                for r in rows
            ),
            "unsafe_authorizations_recorded": sum(
                r.get("unsafe_at_authorization", False)
                and r.get("final_authorization") == "ALLOW"
                for r in rows
            ),
            "execution_violations_recorded": sum(
                r.get("execution_violation", False)
                for r in rows
            ),
            "pilot_excluded": True,
        })

        finish_hashes(out)

    require(
        complete,
        "Formal C1 incomplete; preserve all evidence",
    )


if __name__ == "__main__":
    main()
