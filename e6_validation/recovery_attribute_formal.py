"""E6-2A: four additional archive-eligible attribute configurations.

16 native episodes. T0 controlled evidence routing.
Exact archived DeepSeek plans; no online model generation.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import traceback
from pathlib import Path

from e4_validation.simulator import start_controller
from e5_validation.common import (
    CATALOGUE, ROOT, append_jsonl, file_sha, finish_hashes,
    read_json, read_jsonl, require, write_json,
)
from e5_validation.task_recovery_v2 import load_cache, lookup
from e6_validation.recovery_pilot import (
    ARMS,
    CASE_ID as PILOT_CASE,
    FREEZE as PILOT_FREEZE,
    check as check_pilot,
    paired_public,
    run_episode,
)

CASES = (
    "attribute_FloorPlan6_03",
    "attribute_FloorPlan7_05",
    "attribute_FloorPlan8_07",
    "attribute_FloorPlan5_Pot_01",
)
STATES = ("safe", "unsafe")
BASE = Path("results/E6")

FREEZE = BASE / (
    "08_protocol/"
    "e6_attribute_formal_freeze_20261025_01/manifest.json"
)
ELIGIBILITY = BASE / (
    "07_eligibility/"
    "e6_routing_eligibility_20261025_01/eligibility.json"
)
PILOT_AUDIT = BASE / (
    "06_report/"
    "e6_routing_pilot_audit_20261025_01/audit.json"
)
PILOT_RECORDS = BASE / (
    "05_native/"
    "e6_routing_pilot_20261025_01/records.jsonl"
)
ARCHIVE = Path(
    "results/E5/task_recovery/native_20261023_02/episodes"
)

SOURCES = (
    "e6_validation/recovery_attribute_formal.py",
    "e6_validation/recovery_attribute_formal_audit.py",
    "e6_validation/recovery_pilot.py",
    "e6_validation/recovery_pilot_audit.py",
    "e5_validation/task_recovery_v2.py",
    "e5_validation/protocol.py",
    "e5_validation/common.py",
    "e4_validation/protocol.py",
    "e4_validation/simulator.py",
    "e4_validation/llm_shadow.py",
    str(CATALOGUE),
    str(ELIGIBILITY),
    str(PILOT_AUDIT),
    str(PILOT_RECORDS),
    str(PILOT_FREEZE),
)


def selected_cases():
    catalogue = read_jsonl(ROOT / CATALOGUE)
    by_id = {c["case_id"]: c for c in catalogue}

    require(
        len(by_id) == len(catalogue),
        "Duplicate catalogue case ID",
    )
    require(
        PILOT_CASE not in CASES
        and len(set(CASES)) == 4,
        "Pilot case must be excluded",
    )
    require(
        all(
            cid in by_id
            and by_id[cid]["family"] == "attribute"
            for cid in CASES
        ),
        "Unrecognized or non-attribute case",
    )

    return [by_id[cid] for cid in CASES]


def eligible_and_archived():
    pilot_case, _ = check_pilot()

    require(
        pilot_case["case_id"] == PILOT_CASE,
        "Pilot selection changed",
    )

    pilot = read_json(ROOT / PILOT_AUDIT)

    require(
        pilot["status"] == "PASS"
        and pilot["audited"] == 4
        and pilot["records_sha256"]
        == file_sha(ROOT / PILOT_RECORDS),
        "Pilot audit does not match Pilot run",
    )

    report = read_json(ROOT / ELIGIBILITY)

    require(
        report["status"] == "INSPECTION_COMPLETE"
        and len(report["rows"]) == 16,
        "Eligibility record changed",
    )

    available = {
        (row["case_id"], row["initial_state"])
        for row in report["rows"]
        if row["eligible"]
    }

    expected = {
        (cid, label)
        for cid in (*CASES, PILOT_CASE)
        for label in STATES
    }

    require(
        available == expected,
        "Eligibility not precisely the five attribute cases",
    )

    cache = load_cache()
    cases = selected_cases()
    inputs = {}

    for case in cases:
        for label in STATES:
            folder = (
                ROOT / ARCHIVE
                / case["case_id"]
                / label
                / "G3_shared_safety_or_native_replan"
            )

            names = (
                "planner_initial_input.json",
                "plan_00.json",
                "recovery_observation.json",
                "plan_01.json",
            )

            snapshots = {
                name: read_json(folder / name)
                for name in names
            }

            original = snapshots["plan_00.json"]
            repaired = snapshots["plan_01.json"]
            fresh = snapshots["recovery_observation.json"]
            polluted = paired_public(fresh, case)

            require(
                lookup(
                    snapshots["planner_initial_input.json"],
                    case, cache,
                )["request_sha256"]
                == original["request_sha256"],
                "Initial archived plan mismatch",
            )

            require(
                lookup(
                    polluted, case, cache,
                )["request_sha256"]
                == original["request_sha256"],
                "Same-source archived plan mismatch",
            )

            require(
                lookup(
                    fresh, case, cache,
                )["request_sha256"]
                == repaired["request_sha256"],
                "Protected archived plan mismatch",
            )

            require(
                original["request_sha256"]
                != repaired["request_sha256"],
                "Recovery conditions do not produce different plans",
            )

            inputs[f"{case['case_id']}/{label}"] = {
                str((folder / name).relative_to(ROOT)):
                    file_sha(folder / name)
                for name in names
            }

    return cases, cache, inputs


def preregister():
    require(
        not (ROOT / FREEZE).exists(),
        "Formal protocol already frozen",
    )

    cases, _, inputs = eligible_and_archived()

    write_json(ROOT / FREEZE, {
        "schema": "e6.attribute_recovery_routing_formal.v1",
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "cases": [
            case["case_id"] for case in cases
        ],
        "states": list(STATES),
        "arms": list(ARMS),
        "episodes": 16,
        "pilot_excluded": True,
        "sampling": (
            "All four additional archive-eligible "
            "attribute development configurations"
        ),
        "exclusions": (
            "Six relation condition rows have "
            "NO_HISTORICAL_RECOVERY"
        ),
        "threat_level": "T0 controlled-copy only",
        "model": (
            "Exact archived original DeepSeek responses; "
            "no online regeneration"
        ),
        "guard": (
            "Protected native Pass before each candidate"
        ),
        "recovery_budget": (
            "One additional protected Pass for both arms"
        ),
        "independent_case_count": 4,
        "source_sha256": {
            path: file_sha(ROOT / path)
            for path in SOURCES
        },
        "archive_sha256_by_case_state": inputs,
    })

    print(
        "E6-2A ATTRIBUTE FORMAL FROZEN:",
        ROOT / FREEZE,
    )


def check():
    frozen = read_json(ROOT / FREEZE)

    require(
        frozen["cases"] == list(CASES)
        and frozen["states"] == list(STATES)
        and frozen["arms"] == list(ARMS)
        and frozen["episodes"] == 16
        and frozen["pilot_excluded"] is True,
        "Formal assignment changed",
    )

    for source, expected in frozen["source_sha256"].items():
        require(
            file_sha(ROOT / source) == expected,
            "Frozen source changed: " + source,
        )

    cases, cache, inputs = eligible_and_archived()

    require(
        inputs == frozen["archive_sha256_by_case_state"],
        "Historical archived prompts changed",
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
        preregister()
        return

    require(args.out, "--out is required")

    cases, cache = check()
    out = (ROOT / args.out).resolve()

    require(
        out.is_relative_to(ROOT / BASE)
        and not out.exists(),
        "Output must be NEW under results/E6",
    )

    out.mkdir(parents=True, exist_ok=False)

    write_json(out / "run_manifest.json", {
        "protocol": str(FREEZE),
        "protocol_sha256": file_sha(ROOT / FREEZE),
        "mode": (
            "dryrun" if args.dry_run
            else "native_formal"
        ),
        "cases": list(CASES),
        "states": list(STATES),
        "arms": list(ARMS),
        "expected_episodes": 16,
        "pilot_excluded": True,
        "online_llm_calls": 0,
    })

    if args.dry_run:
        write_json(out / "summary.json", {
            "status": "PASS",
            "archive_pairs": 8,
            "planned_episodes": 16,
            "Unity_calls": 0,
            "LLM_calls": 0,
        })

        finish_hashes(out)

        print(
            "E6-2A ATTRIBUTE FORMAL DRY RUN: PASS "
            "(16 trials, zero Unity/API)"
        )
        return

    rows = []
    controller = None

    try:
        controller = start_controller(
            cases[0]["scene"]
        )

        for case in cases:
            for label in STATES:
                for arm in ARMS:
                    folder = (
                        out / "episodes"
                        / case["case_id"]
                        / label
                        / arm
                    )

                    try:
                        row = run_episode(
                            controller,
                            case,
                            label == "safe",
                            arm,
                            folder,
                            cache,
                        )

                        require(
                            row["recovery_count"] == 1,
                            "Recovery was not triggered",
                        )
                        require(
                            row["recovery_protected_query_count"]
                            == 1,
                            "Unexpected recovery query budget",
                        )

                    except Exception as exc:
                        folder.mkdir(
                            parents=True,
                            exist_ok=True,
                        )

                        row = {
                            "case_id": case["case_id"],
                            "arm": arm,
                            "safe_initial": label == "safe",
                            "status": "FAILED_OR_INCOMPLETE",
                            "error": repr(exc),
                            "traceback": traceback.format_exc(),
                            "evidence_dir": str(
                                folder.relative_to(ROOT)
                            ),
                        }

                        write_json(
                            folder / "failure.json",
                            row,
                        )

                    rows.append(row)
                    append_jsonl(
                        out / "records.jsonl",
                        row,
                    )

                    print(
                        f"{len(rows)}/16 "
                        f"{case['case_id']} "
                        f"{label} {arm} "
                        f"status={row['status']} "
                        f"safe_task={row.get('safe_task_success')} "
                        f"UAR={row.get('UAR')} "
                        f"violation={row.get('execution_violation')}",
                        flush=True,
                    )

    finally:
        if controller is not None:
            controller.stop()

        completed = (
            len(rows) == 16
            and all(
                row["status"] == "COMPLETED"
                for row in rows
            )
        )

        write_json(out / "summary.json", {
            "complete": completed,
            "attempted": len(rows),
            "expected": 16,
            "status_counts": dict(
                collections.Counter(
                    row["status"] for row in rows
                )
            ),
            "safe_task_successes": sum(
                bool(row.get("safe_task_success", False))
                for row in rows
            ),
            "UAR": sum(
                bool(row.get("UAR", False))
                for row in rows
            ),
            "execution_violations": sum(
                bool(row.get("execution_violation", False))
                for row in rows
            ),
            "recovery_queries": sum(
                row.get(
                    "recovery_protected_query_count", 0
                )
                for row in rows
            ),
            "guard_queries": sum(
                row.get(
                    "guard_protected_query_count", 0
                )
                for row in rows
            ),
            "pilot_excluded": True,
        })

        finish_hashes(out)

    require(
        completed,
        "E6 attribute formal incomplete; preserve evidence",
    )


if __name__ == "__main__":
    main()
