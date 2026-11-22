"""Read-only cross-stage E5-C evidence consolidation."""
from __future__ import annotations

import json
from pathlib import Path

from e5_validation.common import (
    ROOT, file_sha, read_json, read_jsonl,
)

BASE = Path("results/E5/C_temporal_validity")
OUT = BASE / "28_final/e5_c_final_20261025_01"

STAGES = {
    "C1": {
        "run": BASE / "07_native/c1_formal_20261024_01",
        "audit": BASE / "08_report/c1_formal_audit_20261024_01/summary.json",
        "freeze": BASE / "05_protocol/c1_formal_freeze_20261024_01/manifest.json",
        "n": 15,
        "cases": 5,
    },
    "C2": {
        "run": BASE / "26_native/c2_formal_20261024_01",
        "audit": BASE / "27_report/c2_formal_audit_20261024_01/summary.json",
        "freeze": BASE / "24_protocol/c2_formal_freeze_20261024_01/manifest.json",
        "n": 9,
        "cases": 3,
    },
    "C3": {
        "run": BASE / "17_native/c3_formal_20261024_01",
        "audit": BASE / "18_report/c3_formal_audit_20261024_01/summary.json",
        "freeze": BASE / "15_protocol/c3_formal_freeze_20261024_01/manifest.json",
        "n": 30,
        "cases": 5,
    },
}


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def verify_group(groups, key, expected):
    require(key in groups, f"Missing group: {key}")
    actual = groups[key]

    for metric, value in expected.items():
        require(
            actual.get(metric) == value,
            f"{key}: {metric} "
            f"expected={value}, found={actual.get(metric)}",
        )


def main():
    out = ROOT / OUT
    require(not out.exists(), "Output already exists")

    evidence = {}
    case_sets = {}

    for stage, cfg in STAGES.items():
        run = ROOT / cfg["run"]
        report = read_json(ROOT / cfg["audit"])
        frozen = read_json(ROOT / cfg["freeze"])
        manifest = read_json(run / "run_manifest.json")
        records = read_jsonl(run / "records.jsonl")

        require(
            report["status"] == "PASS"
            and report["audited"] == cfg["n"],
            f"{stage}: audit not passed",
        )
        require(
            report["records_sha256"]
            == file_sha(run / "records.jsonl"),
            f"{stage}: evidence checksum changed",
        )
        require(
            report["source_run"] == str(cfg["run"]),
            f"{stage}: audit source mismatch",
        )
        require(
            len(records) == cfg["n"]
            and all(r["status"] == "COMPLETED" for r in records),
            f"{stage}: incomplete formal run",
        )
        require(
            manifest["protocol_sha256"]
            == file_sha(ROOT / cfg["freeze"]),
            f"{stage}: frozen protocol mismatch",
        )
        require(
            manifest["pilot_excluded"] is True,
            f"{stage}: pilot exclusion not verified",
        )

        for source, expected in frozen["source_sha256"].items():
            require(
                file_sha(ROOT / source) == expected,
                f"{stage}: frozen source changed: {source}",
            )

        cases = {r["case_id"] for r in records}
        require(
            len(cases) == cfg["cases"],
            f"{stage}: wrong case count",
        )

        case_sets[stage] = cases
        evidence[stage] = {
            "run": str(cfg["run"]),
            "audit": str(cfg["audit"]),
            "records_sha256": report["records_sha256"],
            "episodes": cfg["n"],
            "case_ids": sorted(cases),
            "comparison": report["comparison"],
        }

        print(
            f"{stage}: episodes={cfg['n']} "
            f"cases={len(cases)} "
            "hashes=PASS",
            flush=True,
        )

    require(
        case_sets["C1"] == case_sets["C3"],
        "C1/C3 case reuse mismatch",
    )
    require(
        case_sets["C1"].isdisjoint(case_sets["C2"]),
        "Attribute/relation case overlap",
    )

    # C1: attribute temporal invalidation.
    c1 = {
        row["arm"]: row
        for row in evidence["C1"]["comparison"]
    }

    for arm, metrics in {
        "C1_0_static": (0, 0, 5, 0),
        "C1_1_stale": (5, 5, 0, 0),
        "C1_2_fresh": (0, 0, 0, 5),
    }.items():
        uar, violation, safe, queries = metrics

        verify_group(c1, arm, {
            "n": 5,
            "UAR": uar,
            "execution_violation": violation,
            "safe_task_success": safe,
            "extra_fresh_passes": queries,
        })

    # C2: object-relation temporal invalidation.
    c2 = {
        row["arm"]: row
        for row in evidence["C2"]["comparison"]
    }

    for arm, metrics in {
        "C2_0_static": (0, 0, 3, 3, 0),
        "C2_1_stale": (3, 3, 0, 3, 0),
        "C2_2_fresh": (0, 0, 0, 0, 3),
    }.items():
        uar, violation, safe, native, queries = metrics

        verify_group(c2, arm, {
            "n": 3,
            "UAR": uar,
            "execution_violation": violation,
            "safe_task_success": safe,
            "native_toggle_success": native,
            "extra_fresh_pass": queries,
        })

    # C3: conditional notice-driven validity.
    c3 = {
        (row["condition"], row["arm"]): row
        for row in evidence["C3"]["comparison"]
    }

    conditions = (
        "OFF_complete",
        "ON_complete",
        "ON_withheld",
    )

    arms = (
        "C3_1_invalidate_only",
        "C3_2_notify_then_fresh",
    )

    for condition in conditions:
        for arm in arms:
            off = condition == "OFF_complete"

            queries = (
                5 if not off
                and arm == "C3_2_notify_then_fresh"
                else 0
            )

            verify_group(c3, (condition, arm), {
                "n": 5,
                "UAR": 0,
                "execution_violation": 0,
                "safe_task_success": 5 if off else 0,
                "notification_complete": (
                    0 if condition == "ON_withheld"
                    else 5
                ),
                "extra_fresh_pass": queries,
            })

    require(
        sum(x["episodes"] for x in evidence.values()) == 54,
        "Unexpected total number of formal episodes",
    )

    limitations = [
        "Experiment-controlled sequential T0 changes, not concurrent TOCTOU or a T1 native attacker.",
        "Original archived DeepSeek plans, not online LLM regeneration.",
        "Eight reused development configurations, not independent heldout cases.",
        "C3 completeness assumes a controlled single-writer notice path.",
        "C3 explicitly signaled incomplete streams; silent unmarked losses were not detected.",
        "An Always-Fresh comparison of 15 queries is hypothetical, not a newly executed baseline.",
    ]

    summary = {
        "status": "PASS",
        "type": "read_only_cross_stage_audit",
        "formal_native_episodes": 54,
        "distinct_case_configurations": 8,
        "pilot_excluded": True,
        "C1_C2_stale_UAR": 8,
        "C1_C2_stale_execution_violations": 8,
        "C1_C2_fresh_UAR": 0,
        "C1_C2_fresh_execution_violations": 0,
        "C1_C2_static_safe_task_success": 8,
        "C3_UAR": 0,
        "C3_execution_violations": 0,
        "C3_notify_then_fresh_extra_queries": 10,
        "C3_notify_then_fresh_episodes": 15,
        "stages": evidence,
        "limitations": limitations,
    }

    out.mkdir(parents=True, exist_ok=False)

    (out / "summary.json").write_text(
        json.dumps(
            summary, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# E5-C Final Evidence Summary",
        "",
        "Cross-stage audit: PASS",
        "",
        "| Stage | Formal episodes | Main result |",
        "|---|---:|---|",
        "| C1 | 15 | Stale: 5/5 UAR and executed violations |",
        "| C2 | 9 | Stale: 3/3 UAR and executed violations |",
        "| C3 | 30 | Zero UAR and violations under conditional notice assumptions |",
        "",
        "**Total: 54 formal episodes across 8 reused configurations.**",
        "",
        "C1+C2: Stale 8/8 violations; Fresh 0/8;",
        "Static 8/8 safe task completions.",
        "",
        "C3: Notify-Then-Fresh used 10 extra Pass queries",
        "over 15 episodes; unconditional 15-query comparison",
        "was not separately executed.",
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in limitations],
        "",
    ]

    (out / "report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\nE5-C FINAL CROSS-STAGE AUDIT: PASS")
    print("Formal episodes: 54")
    print("Distinct reused case configurations: 8")
    print("C1+C2 Stale: 8/8 UAR and native violations")
    print("C1+C2 Fresh: 0/8 UAR and native violations")
    print("C3: 0/30 UAR or native violations")
    print("Output:", out)


if __name__ == "__main__":
    main()
