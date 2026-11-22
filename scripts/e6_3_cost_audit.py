"""E6-3: native query, execution and recovery cost audit.

Only consumes independently audited E6-2A formal evidence.
No Unity or online LLM calls.
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUN = ROOT / (
    "results/E6/10_native/"
    "e6_attribute_formal_20261025_01"
)
AUDIT = ROOT / (
    "results/E6/11_report/"
    "e6_attribute_formal_audit_20261025_01/audit.json"
)
OUT = ROOT / (
    "results/E6/13_cost/"
    "e6_cost_audit_20261025_01"
)

ARMS = (
    "E6_R1_same_source_replan",
    "E6_R2_protected_replan",
)


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ms(ns):
    require(
        type(ns) in (int, float) and ns >= 0,
        "Invalid nonnegative nanosecond measurement",
    )
    return ns / 1e6


def median(items, key):
    return round(statistics.median(
        item[key] for item in items
    ), 3)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0])
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    require(not OUT.exists(), "E6-3 output already exists")

    audit = read(AUDIT)
    records_path = RUN / "records.jsonl"

    require(
        audit["status"] == "PASS"
        and audit["audited"] == 16
        and audit["pilot_excluded"] is True
        and audit["records_sha256"] == sha(records_path),
        "Source not independently audited or has changed",
    )

    records = [
        json.loads(line)
        for line in records_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    require(
        len(records) == 16
        and all(r["status"] == "COMPLETED" for r in records),
        "Formal run incomplete",
    )

    episodes = []
    groups = defaultdict(dict)

    for row in records:
        folder = ROOT / row["evidence_dir"]
        require(
            folder.is_relative_to(RUN / "episodes"),
            "Unexpected source evidence path",
        )
        require(
            read(folder / "episode.json") == row,
            "Episode row differs from source file",
        )
        require(
            row["arm"] in ARMS
            and row["online_llm_calls"] == 0
            and row["recovery_count"] == 1
            and row["recovery_protected_query_count"] == 1,
            "Protocol or query budget changed",
        )

        guard_ns = 0
        navigation_ns = 0
        execution_ns = 0
        submitted = 0

        for index, brief in enumerate(row["steps"]):
            item = read(
                folder / f"step_{index:02d}.json"
            )

            require(
                item["candidate"] == brief["candidate"]
                and item["index"] == index,
                "Step record mismatch",
            )

            query = item["guard_query"]

            require(
                query is not None
                and query["receipt"]["success"] is True
                and query["receipt"]["last_action"] == "Pass"
                and query["request_monotonic_ns"]
                    <= query["response_monotonic_ns"],
                "Guard protected query evidence invalid",
            )

            guard_ns += query["query_ns"]
            navigation_ns += item["navigation_ns"]
            execution_ns += item["execution_ns"]
            submitted += int(item["submitted"])

        recovery = read(folder / "recovery_query.json")

        require(
            recovery["receipt"]["success"] is True
            and recovery["receipt"]["last_action"] == "Pass",
            "Recovery protected Pass invalid",
        )

        task_ms = ms(row["task_ns"])

        item = {
            "case_id": row["case_id"],
            "state": (
                "safe" if row["safe_initial"]
                else "unsafe"
            ),
            "arm": row["arm"],
            "safe_task_success": int(
                row["safe_task_success"]
            ),
            "UAR": int(row["UAR"]),
            "execution_violation": int(
                row["execution_violation"]
            ),
            "steps": len(row["steps"]),
            "native_submissions": submitted,
            "guard_queries": len(row["steps"]),
            "recovery_queries": 1,
            "guard_query_ms": round(ms(guard_ns), 3),
            "recovery_query_ms": round(
                ms(recovery["query_ns"]), 3
            ),
            "navigation_ms": round(
                ms(navigation_ns), 3
            ),
            "native_execution_ms": round(
                ms(execution_ns), 3
            ),
            "episode_wall_ms": round(task_ms, 3),
        }

        measured = (
            item["guard_query_ms"]
            + item["recovery_query_ms"]
            + item["navigation_ms"]
            + item["native_execution_ms"]
        )

        # Do not call the remaining time Monitor or LLM latency.
        # It also includes Python/Unity setup, state collection,
        # logging and other uninstrumented work.
        item["other_wall_ms"] = round(
            task_ms - measured, 3
        )

        episodes.append(item)

        key = (item["case_id"], item["state"])
        require(
            row["arm"] not in groups[key],
            "Duplicate paired arm",
        )
        groups[key][row["arm"]] = item

    require(
        len(groups) == 8,
        "Expected eight independent case-state pairs",
    )

    pairs = []

    numeric = (
        "steps",
        "native_submissions",
        "guard_queries",
        "recovery_queries",
        "guard_query_ms",
        "recovery_query_ms",
        "navigation_ms",
        "native_execution_ms",
        "episode_wall_ms",
        "other_wall_ms",
    )

    for (case, state), pair in sorted(groups.items()):
        require(
            set(pair) == set(ARMS),
            "Missing paired R1/R2 arm",
        )

        r1, r2 = (pair[a] for a in ARMS)

        require(
            r1["recovery_queries"]
            == r2["recovery_queries"] == 1,
            "Unequal recovery budgets",
        )

        pairs.append({
            "case_id": case,
            "state": state,
            "r1_success": r1["safe_task_success"],
            "r2_success": r2["safe_task_success"],
            **{
                f"delta_r2_minus_r1_{field}":
                round(r2[field] - r1[field], 3)
                for field in numeric
            },
        })

    summary = []

    for arm in ARMS:
        rows = [
            item for item in episodes
            if item["arm"] == arm
        ]

        require(len(rows) == 8, "Wrong arm denominator")

        summary.append({
            "arm": arm,
            "n": 8,
            "safe_task_successes": sum(
                x["safe_task_success"] for x in rows
            ),
            "UAR": sum(x["UAR"] for x in rows),
            "execution_violations": sum(
                x["execution_violation"] for x in rows
            ),
            "guard_queries": sum(
                x["guard_queries"] for x in rows
            ),
            "recovery_queries": sum(
                x["recovery_queries"] for x in rows
            ),
            "median_guard_query_ms": median(
                rows, "guard_query_ms"
            ),
            "median_recovery_query_ms": median(
                rows, "recovery_query_ms"
            ),
            "median_navigation_ms": median(
                rows, "navigation_ms"
            ),
            "median_native_execution_ms": median(
                rows, "native_execution_ms"
            ),
            "median_episode_wall_ms": median(
                rows, "episode_wall_ms"
            ),
        })

    result = {
        "status": "PASS",
        "scope": "E6-2A audited formal only",
        "episodes": 16,
        "paired_case_states": 8,
        "new_unity_calls": 0,
        "new_llm_calls": 0,
        "source_audit_sha256": sha(AUDIT),
        "source_records_sha256": sha(records_path),
        "comparison": summary,
        "pair_differences": pairs,
        "limitations": [
            "Episode wall time includes simulator setup.",
            "No online LLM inference time was measured.",
            "Protected Pass reads same-Unity authoritative metadata.",
            "Other wall time is not Monitor inference latency.",
            "Four development cases, not independent heldout.",
            "CPU software-rendering timings are platform-specific.",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=False)

    write_csv(OUT / "episodes.csv", episodes)
    write_csv(OUT / "paired_differences.csv", pairs)
    write_csv(OUT / "comparison.csv", summary)

    (OUT / "summary.json").write_text(
        json.dumps(
            result, ensure_ascii=False, indent=2
        ) + "\n",
        encoding="utf-8",
    )

    for item in summary:
        print(item, flush=True)

    print(
        "\nMedian paired R2-R1 episode difference (ms):",
        round(statistics.median(
            p["delta_r2_minus_r1_episode_wall_ms"]
            for p in pairs
        ), 3),
    )
    print("E6-3 COST AUDIT: PASS")
    print("New Unity calls: 0")
    print("New LLM calls: 0")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
