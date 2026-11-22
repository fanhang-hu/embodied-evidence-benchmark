"""E6-1: normalize audited metrics and locate recovery evidence.

Read-only inputs. No Unity or LLM execution.
Does not pool incompatible experimental denominators.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E5 = Path("results/E5/C_temporal_validity")
SCOPE = Path(
    "results/E6/00_scope/"
    "e6_scope_20261025_01/scope_manifest.json"
)
FINAL = E5 / "28_final/e5_c_final_20261025_01/summary.json"
OUT = Path("results/E6/01_metrics/e6_metrics_20261025_01")

EXPECTED = {
    "C1": {
        "n": 15,
        "group_n": 5,
        "query_key": "extra_fresh_passes",
    },
    "C2": {
        "n": 9,
        "group_n": 3,
        "query_key": "extra_fresh_pass",
    },
    "C3": {
        "n": 30,
        "group_n": 5,
        "query_key": "extra_fresh_pass",
    },
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def read(path):
    return json.loads(
        (ROOT / path).read_text(encoding="utf-8")
    )


def digest(path):
    h = hashlib.sha256()
    with (ROOT / path).open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def jsonl(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def inventory(directory, maximum=35):
    base = ROOT / directory
    if not base.is_dir():
        return []

    found = []
    for filename in (
        "records.jsonl",
        "summary.json",
        "acceptance.json",
        "comparison.csv",
        "audit.json",
    ):
        for path in base.rglob(filename):
            if len(found) >= maximum:
                break

            item = {
                "path": str(path.relative_to(ROOT)),
                "size_bytes": path.stat().st_size,
            }

            if filename.endswith(".jsonl"):
                with path.open(encoding="utf-8") as f:
                    first = next(
                        (line for line in f if line.strip()),
                        None,
                    )
                if first:
                    try:
                        sample = json.loads(first)
                        item["row_keys"] = (
                            sorted(sample)
                            if isinstance(sample, dict)
                            else []
                        )
                    except ValueError:
                        item["parse_error"] = True

            elif filename.endswith(".json"):
                try:
                    sample = json.loads(
                        path.read_text(encoding="utf-8")
                    )
                    item["root_keys"] = (
                        sorted(sample)
                        if isinstance(sample, dict)
                        else []
                    )
                except (ValueError, UnicodeError):
                    item["parse_error"] = True

            found.append(item)

        if len(found) >= maximum:
            break

    return found


def main():
    require(
        not (ROOT / OUT).exists(),
        "STOP: E6-1 output already exists",
    )

    scope = read(SCOPE)
    final = read(FINAL)

    require(
        scope["status"] == "SCOPE_AUDIT_PASS"
        and scope["E6_completed"] is False
        and scope["native_T1_proven"] is False,
        "E6-0 evidence boundary changed",
    )

    require(
        scope["source_hashes"]["e5_final"] == digest(FINAL),
        "E5 final audit source changed",
    )

    require(
        final["status"] == "PASS"
        and final["formal_native_episodes"] == 54
        and final["pilot_excluded"] is True,
        "E5-C evidence not eligible",
    )

    groups = []
    stage_cases = {}

    for stage, cfg in EXPECTED.items():
        info = final["stages"][stage]
        records = jsonl(
            Path(info["run"]) / "records.jsonl"
        )

        require(
            info["episodes"] == cfg["n"]
            and len(records) == cfg["n"]
            and all(
                row["status"] == "COMPLETED"
                for row in records
            ),
            f"{stage}: wrong or incomplete denominator",
        )

        require(
            digest(
                Path(info["run"]) / "records.jsonl"
            ) == info["records_sha256"],
            f"{stage}: source records changed",
        )

        stage_cases[stage] = {
            row["case_id"] for row in records
        }

        assignments = Counter(
            (
                row.get("condition", "")
                if stage == "C3"
                else "",
                row["arm"],
            )
            for row in records
        )

        comparisons = info["comparison"]

        for comparison in comparisons:
            condition = (
                comparison["condition"]
                if stage == "C3"
                else ""
            )
            arm = comparison["arm"]
            key = (condition, arm)

            require(
                comparison["n"] == cfg["group_n"]
                and assignments[key] == cfg["group_n"],
                f"{stage}/{key}: denominator mismatch",
            )

            for metric in (
                "UAR",
                "execution_violation",
                "safe_task_success",
                cfg["query_key"],
            ):
                require(
                    metric in comparison,
                    f"{stage}/{key}: missing {metric}",
                )

            groups.append({
                "stage": stage,
                "condition": condition,
                "arm": arm,
                "n": comparison["n"],
                "uar_count": comparison["UAR"],
                "violation_count":
                    comparison["execution_violation"],
                "safe_task_success_count":
                    comparison["safe_task_success"],
                "extra_protected_pass_count":
                    comparison[cfg["query_key"]],
                "uar_rate":
                    comparison["UAR"] / comparison["n"],
                "violation_rate":
                    comparison["execution_violation"]
                    / comparison["n"],
                "safe_task_success_rate":
                    comparison["safe_task_success"]
                    / comparison["n"],
                "evidence_type":
                    "native_executed_archived_llm",
                "attacker_level": "T0",
            })

        require(
            set(assignments) == {
                (
                    row["condition"] if stage == "C3" else "",
                    row["arm"],
                )
                for row in comparisons
            },
            f"{stage}: unaccounted experiment groups",
        )

        print(
            f"{stage}: {cfg['n']} episodes, "
            f"{len(comparisons)} groups, metrics=PASS",
            flush=True,
        )

    require(
        len(groups) == 12
        and stage_cases["C1"] == stage_cases["C3"]
        and stage_cases["C1"].isdisjoint(
            stage_cases["C2"]
        ),
        "Cross-stage selection mismatch",
    )

    by_arm = {
        (row["stage"], row["arm"]): row
        for row in groups
        if row["stage"] in ("C1", "C2")
    }

    def total(arms, field):
        return sum(by_arm[key][field] for key in arms)

    static = (
        ("C1", "C1_0_static"),
        ("C2", "C2_0_static"),
    )
    stale = (
        ("C1", "C1_1_stale"),
        ("C2", "C2_1_stale"),
    )
    fresh = (
        ("C1", "C1_2_fresh"),
        ("C2", "C2_2_fresh"),
    )

    require(
        total(static, "safe_task_success_count") == 8
        and total(stale, "uar_count") == 8
        and total(stale, "violation_count") == 8
        and total(fresh, "uar_count") == 0
        and total(fresh, "violation_count") == 0,
        "C1/C2 audited aggregate disagrees",
    )

    c3 = [
        group for group in groups
        if group["stage"] == "C3"
    ]
    require(
        sum(row["uar_count"] for row in c3) == 0
        and sum(row["violation_count"] for row in c3) == 0,
        "C3 audited safety aggregate disagrees",
    )

    # Inventory E4 and earlier recovery evidence without
    # assuming their schemas are identical to E5-C.
    sources = {
        "E4": inventory(Path("results/E4")),
        "E5_task_recovery": inventory(
            Path("results/E5/task_recovery")
        ),
    }

    report = {
        "status": "PASS",
        "scope": "audited_T0_results_only",
        "formal_episodes": 54,
        "unique_development_case_configurations": 8,
        "group_count": len(groups),
        "E4_paired_conditions": 84,
        "E4_not_pooled_with_E5": True,
        "C1_C2_static_safe_task_success": 8,
        "C1_C2_stale_uar": 8,
        "C1_C2_stale_execution_violation": 8,
        "C1_C2_fresh_uar": 0,
        "C1_C2_fresh_execution_violation": 0,
        "C3_all_uar": 0,
        "C3_all_execution_violation": 0,
        "groups": groups,
        "next_research_gap": (
            "Planner recovery, benign utility, "
            "same-source versus independent-query "
            "permission parity, end-to-end costs"
        ),
        "limitations": [
            "54 episodes are not 54 independent scenes",
            "Prior development configurations, not heldout",
            "Archived DeepSeek actions, not online replanning",
            "C3 complete-notice claim assumes exclusive writer",
            "C3 withheld events were explicitly marked incomplete",
            "Safety denial is not equivalent to task recovery",
            "E4 deterministic planner cannot be pooled with E5",
        ],
    }

    output = ROOT / OUT
    output.mkdir(parents=True, exist_ok=False)

    (output / "metrics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with (output / "group_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(groups[0])
        )
        writer.writeheader()
        writer.writerows(groups)

    (output / "source_inventory.json").write_text(
        json.dumps(
            sources, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    print()
    print("E6-1 METRIC HARMONIZATION: PASS")
    print("C1+C2: stale 8/8 UAR, 8/8 violations")
    print("C1+C2: fresh 0/8 UAR, 0/8 violations")
    print("C3: 0/30 UAR and violations")
    print()
    print("E4 evidence candidates:")
    for item in sources["E4"][:12]:
        print(" ", item["path"])
    print("Recovery evidence candidates:")
    for item in sources["E5_task_recovery"][:12]:
        print(" ", item["path"])
    print("Output:", output)


if __name__ == "__main__":
    main()
