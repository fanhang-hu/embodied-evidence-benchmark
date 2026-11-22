"""E5-C C3 five-configuration native paired experiment.

Reuses the frozen and independently audited C3 Pilot run_episode unchanged.
Does not overwrite the six-episode Pilot or any prior C1 source.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import traceback

from e4_validation.protocol import critical_action
from e4_validation.simulator import start_controller
from e5_validation.a_consistent_pollution.runner import check_protocol as check_a
from e5_validation.c_temporal.c3_pilot import (
    ARMS, CONDITIONS, check as check_pilot, run_episode,
)
from e5_validation.common import (
    ROOT, append_jsonl, file_sha, finish_hashes, new_output,
    read_json, require, write_json,
)
from e5_validation.task_recovery_v2 import load_cache, lookup

BASE = "results/E5/C_temporal_validity"
FROZEN = BASE + "/15_protocol/c3_formal_freeze_20261024_01/manifest.json"
PILOT_FREEZE = BASE + "/11_protocol/c3_pilot_freeze_20261024_01/manifest.json"
PILOT_RUN = BASE + "/13_pilot/c3_native_20261024_01/records.jsonl"
PILOT_AUDIT = BASE + "/14_report/c3_pilot_audit_20261024_01/audit.json"
A_CLEAN = "results/E5/A_consistent_pollution/02_native/run_20261024_01"

SOURCES = (
    "e5_validation/c_temporal/c3_formal.py",
    "e5_validation/c_temporal/c3_formal_audit.py",
    "e5_validation/c_temporal/c3_pilot.py",
    "e5_validation/c_temporal/c3_pilot_audit.py",
    "e5_validation/c_temporal/c3_notice_policy.py",
    "e5_validation/c_temporal/c3_notice_adapter.py",
    "e4_validation/protocol.py",
    "e4_validation/simulator.py",
    "e5_validation/common.py",
    "e5_validation/task_recovery_v2.py",
    "e5_validation/a_consistent_pollution/runner.py",
    PILOT_FREEZE,
    PILOT_RUN,
    PILOT_AUDIT,
    BASE + "/10_notification_preflight/notice_preflight_20261024_01/summary.json",
)


def exact_off_plan(case, cache):
    source = (
        ROOT / A_CLEAN / "episodes" / case["case_id"]
        / "true_off" / "A0_clean"
    )
    public = read_json(source / "S_planner.json")
    saved = read_json(source / "llm_plan.json")
    plan = lookup(public, case, cache)
    require(
        plan["actions"] == [critical_action(case)]
        and all(plan[k] == saved[k] for k in (
            "request_sha256", "prompt_sha256", "raw_actions"
        )),
        "Original clean-OFF archived LLM response mismatch: " + case["case_id"],
    )
    return plan


def pilot_gate():
    pilot_case = check_pilot()
    report = read_json(ROOT / PILOT_AUDIT)
    require(
        report["status"] == "PASS"
        and report["audited"] == 6
        and report["records_sha256"] == file_sha(ROOT / PILOT_RUN),
        "Pilot independent audit not verified against original data",
    )
    return pilot_case


def freeze():
    require(not (ROOT / FROZEN).exists(), "Formal protocol already exists")
    pilot_case = pilot_gate()
    _, cases = check_a()
    cache = load_cache()
    require(len(cases) == 5 and cases[0]["case_id"] == pilot_case["case_id"],
            "Expected frozen five-case selection")
    plan_ids = {
        c["case_id"]: exact_off_plan(c, cache)["request_sha256"]
        for c in cases
    }
    hashes = {path: file_sha(ROOT / path) for path in SOURCES}
    write_json(ROOT / FROZEN, {
        "schema": "e5.c.c3.notice_formal.v1",
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "case_ids": [c["case_id"] for c in cases],
        "conditions": list(CONDITIONS),
        "arms": list(ARMS),
        "episodes": len(cases) * len(CONDITIONS) * len(ARMS),
        "request_sha256_by_case": plan_ids,
        "source_sha256": hashes,
        "pilot_excluded": True,
        "conditional_single_writer_assumption": True,
        "capture_to_proxy_activation_gap": (
            "Synchronous archived plan lookup before proxy activation; "
            "no other writer assumed during this interval"
        ),
        "notice_stream_sequence": (
            "Python proxy ordinal, not authenticated Unity event sequence"
        ),
        "withheld_control": (
            "Deliberate loss with EXPLICIT incomplete flag, not silent loss"
        ),
        "scope": (
            "T0 experimental same-process notification upper bound; "
            "no deployed trust infrastructure"
        ),
        "online_llm_calls": 0,
        "replanning": False,
    })
    print("E5-C C3 FORMAL PROTOCOL FROZEN:", ROOT / FROZEN)


def check():
    pilot_case = pilot_gate()
    _, cases = check_a()
    manifest = read_json(ROOT / FROZEN)
    require(
        manifest["case_ids"] == [c["case_id"] for c in cases]
        and len(cases) == 5
        and cases[0]["case_id"] == pilot_case["case_id"]
        and manifest["conditions"] == list(CONDITIONS)
        and manifest["arms"] == list(ARMS)
        and manifest["episodes"] == 30,
        "Formal cases or arm assignment changed",
    )
    for path, expected in manifest["source_sha256"].items():
        require(
            file_sha(ROOT / path) == expected,
            "Frozen source changed: " + path,
        )
    cache = load_cache()
    for case in cases:
        require(
            exact_off_plan(case, cache)["request_sha256"]
            == manifest["request_sha256_by_case"][case["case_id"]],
            "Frozen plan differs: " + case["case_id"],
        )
    return cases, cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.preregister:
        freeze()
        return

    require(args.out, "--out is required")
    cases, cache = check()
    out = new_output(args.out)
    expected = len(cases) * len(CONDITIONS) * len(ARMS)

    write_json(out / "run_manifest.json", {
        "protocol": FROZEN,
        "protocol_sha256": file_sha(ROOT / FROZEN),
        "case_ids": [c["case_id"] for c in cases],
        "conditions": list(CONDITIONS),
        "arms": list(ARMS),
        "expected_episodes": expected,
        "mode": "dryrun" if args.dry_run else "native_formal",
        "pilot_excluded": True,
        "online_llm_calls": 0,
    })

    if args.dry_run:
        for case in cases:
            plan = exact_off_plan(case, cache)
            for condition in CONDITIONS:
                for arm in ARMS:
                    append_jsonl(out / "records.jsonl", {
                        "case_id": case["case_id"],
                        "condition": condition,
                        "arm": arm,
                        "status": "EXACT_OFF_ARCHIVE_MATCH",
                        "request_sha256": plan["request_sha256"],
                    })
        write_json(out / "summary.json", {
            "matches": expected,
            "unity_calls": 0,
        })
        finish_hashes(out)
        print(
            f"E5-C C3 FORMAL DRY RUN PASS: "
            f"{expected} exact plans; no Unity/API"
        )
        return

    raw_controller = None
    rows = []

    try:
        raw_controller = start_controller(cases[0]["scene"])
        for case in cases:
            for condition in CONDITIONS:
                for arm in ARMS:
                    folder = (
                        out / "episodes" / case["case_id"]
                        / condition / arm
                    )
                    try:
                        row = run_episode(
                            raw_controller, case, condition,
                            arm, folder, cache,
                        )
                    except Exception as exc:
                        folder.mkdir(parents=True, exist_ok=True)
                        row = {
                            "case_id": case["case_id"],
                            "scene": case["scene"],
                            "condition": condition,
                            "arm": arm,
                            "status": "FAILED_OR_INCOMPLETE",
                            "error": repr(exc),
                            "traceback": traceback.format_exc(),
                            "evidence_dir": str(folder.relative_to(ROOT)),
                        }
                        write_json(folder / "failure.json", row)

                    rows.append(row)
                    append_jsonl(out / "records.jsonl", row)
                    print(
                        f"{len(rows)}/{expected} "
                        f"{case['case_id']} {condition} {arm} "
                        f"{row['status']} "
                        f"auth={row.get('final_authorization')} "
                        f"query={row.get('fresh_query_count')} "
                        f"violation={row.get('violation_executed')} "
                        f"safe_task={row.get('safe_task_success')}",
                        flush=True,
                    )

    finally:
        if raw_controller is not None:
            raw_controller.stop()

        complete = (
            len(rows) == expected
            and all(r["status"] == "COMPLETED" for r in rows)
        )
        write_json(out / "summary.json", {
            "complete": complete,
            "recorded": len(rows),
            "expected": expected,
            "status_counts": dict(
                collections.Counter(r["status"] for r in rows)
            ),
            "extra_queries": sum(
                r.get("fresh_query_count", 0) for r in rows
            ),
            "pilot_excluded": True,
            "scope": (
                "Conditional T0, instrumented experimental "
                "single-writer notification path"
            ),
        })
        finish_hashes(out)

    require(complete, "Formal C3 run incomplete; preserve all evidence")


if __name__ == "__main__":
    main()
