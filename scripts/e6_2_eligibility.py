"""E6: read-only eligibility audit for multi-case recovery routing."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from e5_validation.common import (
    ROOT, CATALOGUE, read_json, read_jsonl, require, state,
)
from e5_validation.protocol import paired_view
from e5_validation.task_recovery_v2 import load_cache, lookup

BASE = ROOT / "results/E5/task_recovery/native_20261023_02"
OUT = ROOT / (
    "results/E6/07_eligibility/"
    "e6_routing_eligibility_20261025_01"
)

ARM = "G3_shared_safety_or_native_replan"


def matching_plan(observation, case, cache, plan):
    try:
        result = lookup(observation, case, cache)
        return (
            result["request_sha256"]
            == plan["request_sha256"]
            and result["actions"] == plan["actions"]
        ), ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:180]


def main():
    require(
        not OUT.exists(),
        "STOP: eligibility output already exists",
    )

    cases = read_jsonl(ROOT / CATALOGUE)
    cache = load_cache()
    rows = []

    for case in cases:
        for label in ("safe", "unsafe"):
            folder = (
                BASE / "episodes" / case["case_id"]
                / label / ARM
            )

            row = {
                "case_id": case["case_id"],
                "family": case["family"],
                "initial_state": label,
                "historical_episode_exists":
                    (folder / "episode.json").is_file(),
                "historical_recovery_triggered": False,
                "initial_plan_verified": False,
                "fresh_plan_verified": False,
                "same_source_plan_verified": False,
                "same_source_repeats_initial": False,
                "distinct_corrected_plan": False,
                "eligible": False,
                "reason": "",
            }

            required = (
                "episode.json",
                "planner_initial_input.json",
                "plan_00.json",
            )

            if not all(
                (folder / name).is_file()
                for name in required
            ):
                row["reason"] = "MISSING_HISTORICAL_EPISODE"
                rows.append(row)
                continue

            episode = read_json(folder / "episode.json")
            initial = read_json(
                folder / "planner_initial_input.json"
            )
            original_plan = read_json(folder / "plan_00.json")

            row["historical_recovery_triggered"] = bool(
                episode.get("recovery_triggered", False)
            )

            ok, error = matching_plan(
                initial, case, cache, original_plan
            )

            row["initial_plan_verified"] = ok

            if not ok:
                row["reason"] = "INITIAL_PLAN: " + error
                rows.append(row)
                continue

            if not row["historical_recovery_triggered"]:
                row["reason"] = "NO_HISTORICAL_RECOVERY"
                rows.append(row)
                continue

            if not all(
                (folder / name).is_file()
                for name in (
                    "recovery_observation.json",
                    "plan_01.json",
                )
            ):
                row["reason"] = "MISSING_RECOVERY_EVIDENCE"
                rows.append(row)
                continue

            fresh = read_json(
                folder / "recovery_observation.json"
            )
            corrected_plan = read_json(folder / "plan_01.json")

            ok, error = matching_plan(
                fresh, case, cache, corrected_plan
            )

            row["fresh_plan_verified"] = ok

            if not ok:
                row["reason"] = "FRESH_PLAN: " + error
                rows.append(row)
                continue

            opposite = (
                label == "unsafe"
            )

            candidates = [
                trial for trial in case["trials"]
                if trial["expected_safe"] is opposite
            ]

            if len(candidates) != 1:
                row["reason"] = "OPPOSITE_TRIAL_AMBIGUOUS"
                rows.append(row)
                continue

            try:
                same = paired_view(
                    fresh,
                    case,
                    state(candidates[0]["S_true"]),
                )

                same_plan = lookup(same, case, cache)

                row["same_source_plan_verified"] = True

                row["same_source_repeats_initial"] = (
                    same_plan["request_sha256"]
                    == original_plan["request_sha256"]
                )

            except Exception as exc:
                row["reason"] = (
                    "SAME_SOURCE: "
                    + type(exc).__name__
                    + ": " + str(exc)
                )[:220]
                rows.append(row)
                continue

            row["distinct_corrected_plan"] = (
                corrected_plan["request_sha256"]
                != original_plan["request_sha256"]
            )

            row["eligible"] = bool(
                row["same_source_plan_verified"]
                and row["same_source_repeats_initial"]
                and row["distinct_corrected_plan"]
            )

            row["reason"] = (
                "ARCHIVE_PAIR_VERIFIED"
                if row["eligible"]
                else "PLAN_PAIR_NOT_DISTINCT_OR_NOT_REPEATED"
            )

            rows.append(row)

    require(
        len(rows) == 16,
        "Expected eight cases times two initial states",
    )

    OUT.mkdir(parents=True, exist_ok=False)

    with (OUT / "eligibility.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=list(rows[0])
        )
        writer.writeheader()
        writer.writerows(rows)

    (OUT / "eligibility.json").write_text(
        json.dumps(
            {
                "status": "INSPECTION_COMPLETE",
                "scope": "read_only_archive_eligibility",
                "rows": rows,
                "eligible_count": sum(
                    r["eligible"] for r in rows
                ),
                "new_unity_calls": 0,
                "new_llm_calls": 0,
                "note": (
                    "Archive eligibility alone does not prove "
                    "new native recovery will succeed."
                ),
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print("===== E6 MULTI-CASE ELIGIBILITY =====")

    for row in rows:
        print(
            f"{row['case_id']} "
            f"{row['initial_state']} "
            f"eligible={row['eligible']} "
            f"reason={row['reason']}"
        )

    print()
    print(
        "Eligible archive pairs:",
        sum(r["eligible"] for r in rows),
        "/16"
    )
    print("E6 MULTI-CASE ELIGIBILITY: INSPECTION COMPLETE")
    print("New Unity calls: 0")
    print("New LLM calls: 0")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
