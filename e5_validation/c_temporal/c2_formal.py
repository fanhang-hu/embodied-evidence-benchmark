"""E5-C C2 formal: 3 relation cases x 3 paired native arms.

Reuses the Pilot native episode implementation without source edits.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import traceback

from e4_validation.simulator import start_controller
from e5_validation.c_temporal.c2_pilot import (
    ARMS, CASES, archived_plan, cases as selected_cases,
    check as check_pilot, run_episode,
)
from e5_validation.common import (
    CATALOGUE, ROOT, append_jsonl, file_sha, finish_hashes,
    new_output, read_json, require, write_json,
)
from e5_validation.task_recovery_v2 import load_cache

BASE = "results/E5/C_temporal_validity"
FREEZE = BASE + "/24_protocol/c2_formal_freeze_20261024_01/manifest.json"
PILOT_FREEZE = BASE + "/20_protocol/c2_pilot_freeze_20261024_01/manifest.json"
PILOT_RECORDS = BASE + "/22_pilot/c2_native_20261024_01/records.jsonl"
PILOT_AUDIT = BASE + "/23_report/c2_pilot_audit_20261024_01/audit.json"
C2_PREFLIGHT = BASE + "/19_relation_preflight/c2_plan_preflight_20261024_01/summary.json"
ARCHIVE_BASE = "results/E5/task_recovery/native_20261023_02/episodes"

SOURCES = (
    "e5_validation/c_temporal/c2_formal.py",
    "e5_validation/c_temporal/c2_formal_audit.py",
    "e5_validation/c_temporal/c2_pilot.py",
    "e5_validation/c_temporal/c2_pilot_audit.py",
    "e4_validation/protocol.py",
    "e4_validation/llm_shadow.py",
    "e4_validation/simulator.py",
    "e5_validation/common.py",
    "e5_validation/task_recovery_v2.py",
    "e5_validation/a_consistent_pollution/runner.py",
    str(CATALOGUE),
    "results/E5/00_protocol/task_recovery_20261023_02/manifest.json",
    PILOT_FREEZE,
    PILOT_RECORDS,
    PILOT_AUDIT,
    C2_PREFLIGHT,
)


def archive_sources(items):
    return tuple(
        f"{ARCHIVE_BASE}/{case['case_id']}/safe/G0_clean/{filename}"
        for case in items
        for filename in ("planner_initial_input.json", "plan_00.json")
    )


def pilot_gate():
    case, _ = check_pilot()
    audit = read_json(ROOT / PILOT_AUDIT)

    require(
        audit["status"] == "PASS"
        and audit["audited"] == 3
        and audit["records_sha256"] == file_sha(ROOT / PILOT_RECORDS),
        "C2 Pilot independent audit not verified",
    )
    return case


def freeze():
    require(
        not (ROOT / FREEZE).exists(),
        "Formal protocol already frozen",
    )

    pilot_case = pilot_gate()
    items = selected_cases()

    require(
        [case["case_id"] for case in items] == list(CASES)
        and len(items) == 3
        and pilot_case["case_id"] == CASES[0],
        "C2 case set changed",
    )

    cache = load_cache()

    hashes = {
        path: file_sha(ROOT / path)
        for path in (*SOURCES, *archive_sources(items))
    }

    plans = {
        case["case_id"]: archived_plan(
            case, cache
        )["request_sha256"]
        for case in items
    }

    write_json(ROOT / FREEZE, {
        "schema": "e5.c.c2.native_relation_formal.v1",
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "case_ids": [case["case_id"] for case in items],
        "arms": list(ARMS),
        "episodes": 9,
        "request_sha256_by_case": plans,
        "source_sha256": hashes,
        "pilot_excluded": True,
        "candidate": (
            "third original archived DeepSeek action: ToggleObjectOn"
        ),
        "prefix": (
            "two original unforced PickupObject, PutObject"
        ),
        "experimental_change": (
            "unforced second PickupObject "
            "after protected post-Put Pass"
        ),
        "no_online_llm": True,
        "no_replanning": True,
        "scope": (
            "Sequential experiment-controlled T0 relation change; "
            "not concurrent TOCTOU, target-ID rebinding, "
            "or native T1 attack"
        ),
    })

    print("E5-C C2 FORMAL PROTOCOL FROZEN:", ROOT / FREEZE)


def check():
    pilot_case = pilot_gate()
    items = selected_cases()
    frozen = read_json(ROOT / FREEZE)

    require(
        frozen["case_ids"] == [
            case["case_id"] for case in items
        ]
        and len(items) == 3
        and items[0]["case_id"] == pilot_case["case_id"]
        and frozen["arms"] == list(ARMS)
        and frozen["episodes"] == 9,
        "Formal C2 case, arm, or sample count changed",
    )

    for path, expected in frozen["source_sha256"].items():
        require(
            file_sha(ROOT / path) == expected,
            "C2 formal source changed: " + path,
        )

    cache = load_cache()

    for case in items:
        require(
            archived_plan(case, cache)["request_sha256"]
            == frozen["request_sha256_by_case"][
                case["case_id"]
            ],
            "Archived relation plan changed: " + case["case_id"],
        )

    return items, cache


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

    items, cache = check()
    out = new_output(args.out)

    write_json(out / "run_manifest.json", {
        "protocol": FREEZE,
        "protocol_sha256": file_sha(ROOT / FREEZE),
        "case_ids": [case["case_id"] for case in items],
        "arms": list(ARMS),
        "expected_episodes": 9,
        "mode": (
            "dryrun" if args.dry_run
            else "native_formal"
        ),
        "pilot_excluded": True,
        "online_llm_calls": 0,
    })

    if args.dry_run:
        for case in items:
            plan = archived_plan(case, cache)

            for arm in ARMS:
                append_jsonl(out / "records.jsonl", {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "status": "EXACT_ARCHIVED_THREE_STEP_PLAN",
                    "request_sha256": plan["request_sha256"],
                })

        write_json(out / "summary.json", {
            "matches": 9,
            "unity_calls": 0,
        })

        finish_hashes(out)

        print(
            "E5-C C2 FORMAL DRY RUN PASS: "
            "9 exact plans; no Unity/API"
        )
        return

    controller = None
    rows = []

    try:
        controller = start_controller(items[0]["scene"])

        for case in items:
            for arm in ARMS:
                folder = (
                    out / "episodes" / case["case_id"] / arm
                )

                try:
                    row = run_episode(
                        controller, case, arm,
                        folder, cache,
                    )

                except Exception as error:
                    folder.mkdir(
                        parents=True, exist_ok=True
                    )

                    row = {
                        "case_id": case["case_id"],
                        "arm": arm,
                        "status": "FAILED_OR_INCOMPLETE",
                        "error": repr(error),
                        "traceback": traceback.format_exc(),
                        "evidence_dir": str(
                            folder.relative_to(ROOT)
                        ),
                    }

                    write_json(
                        folder / "failure.json", row
                    )

                rows.append(row)
                append_jsonl(
                    out / "records.jsonl", row
                )

                print(
                    f"{len(rows)}/9 {case['case_id']} {arm} "
                    f"{row['status']} "
                    f"auth={row.get('final_authorization')} "
                    f"UAR={row.get('UAR')} "
                    f"native_toggle={row.get('native_toggle_success')} "
                    f"violation={row.get('execution_violation')} "
                    f"safe_task={row.get('safe_task_success')}",
                    flush=True,
                )

    finally:
        if controller is not None:
            controller.stop()

        complete = (
            len(rows) == 9
            and all(
                row["status"] == "COMPLETED"
                for row in rows
            )
        )

        write_json(out / "summary.json", {
            "complete": complete,
            "expected": 9,
            "recorded": len(rows),
            "status_counts": dict(
                collections.Counter(
                    row["status"] for row in rows
                )
            ),
            "pilot_excluded": True,
            "UAR_recorded": sum(
                row.get("UAR", False) for row in rows
            ),
            "violations_recorded": sum(
                row.get("execution_violation", False)
                for row in rows
            ),
            "native_toggle_failures": sum(
                row.get("native_toggle_failed", False)
                for row in rows
            ),
            "extra_fresh_passes": sum(
                row.get("fresh_query_count", 0)
                for row in rows
            ),
        })

        finish_hashes(out)

    require(
        complete,
        "Formal C2 run incomplete; retain evidence",
    )


if __name__ == "__main__":
    main()
