"""E6-2B: read-only relation planning sensitivity audit.

Checks G3 natural recovery and G4 controlled-DEFER archived plans.
Does not run Unity or LLM. Writes only under results/E6.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from e5_validation.common import (
    ROOT, CATALOGUE, read_json, read_jsonl, require,
)
from e5_validation.task_recovery_v2 import load_cache, lookup

CASES = (
    "relation_FloorPlan6_02",
    "relation_FloorPlan7_04",
    "relation_FloorPlan8_06",
)

BASE = ROOT / (
    "results/E5/task_recovery/native_20261023_02/episodes"
)
OUT = ROOT / (
    "results/E6/12_relation_gate/"
    "e6_relation_gate_20261025_01"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    require(not OUT.exists(), "E6 output already exists")

    catalogue = {
        c["case_id"]: c
        for c in read_jsonl(ROOT / CATALOGUE)
    }
    cache = load_cache()

    rows = []
    sources = {}

    for case_id in CASES:
        case = catalogue[case_id]

        require(
            case["family"] == "relation",
            "Expected relation case",
        )

        for label in ("safe", "unsafe"):
            parent = BASE / case_id / label

            g3 = parent / "G3_shared_safety_or_native_replan"
            g4 = parent / "G4_shared_initial_defer_replan"

            ep3 = read_json(g3 / "episode.json")
            ep4 = read_json(g4 / "episode.json")

            initial = read_json(
                g4 / "planner_initial_input.json"
            )
            fresh = read_json(
                g4 / "recovery_observation.json"
            )

            plan0 = read_json(g4 / "plan_00.json")
            plan1 = read_json(g4 / "plan_01.json")

            cached0 = lookup(initial, case, cache)
            cached1 = lookup(fresh, case, cache)

            for observed, archived in (
                (cached0, plan0),
                (cached1, plan1),
            ):
                require(
                    observed["request_sha256"]
                        == archived["request_sha256"]
                    and observed["actions"]
                        == archived["actions"]
                    and observed["raw_actions"]
                        == archived["raw_actions"],
                    "DeepSeek archive mismatch: "
                    + case_id + "/" + label,
                )

            paths = {
                "G3_episode": g3 / "episode.json",
                "G4_episode": g4 / "episode.json",
                "initial": g4 / "planner_initial_input.json",
                "fresh": g4 / "recovery_observation.json",
                "plan0": g4 / "plan_00.json",
                "plan1": g4 / "plan_01.json",
            }

            for path in paths.values():
                sources[str(path.relative_to(ROOT))] = sha(path)

            recoveries = ep4.get("recoveries", [])

            row = {
                "case_id": case_id,
                "initial_state": label,
                "G3_natural_recovery":
                    bool(ep3.get("recovery_triggered")),
                "G4_recovery":
                    bool(ep4.get("recovery_triggered")),
                "G4_trigger": (
                    recoveries[0].get("trigger")
                    if recoveries else None
                ),
                "original_plan_archived": True,
                "corrected_plan_archived": True,
                "request_changed":
                    plan0["request_sha256"]
                    != plan1["request_sha256"],
                "actions_changed":
                    plan0["actions"] != plan1["actions"],
                "original_actions": plan0["actions"],
                "corrected_actions": plan1["actions"],
                "G4_safe_task_success":
                    bool(ep4.get("safe_task_success")),
            }

            rows.append(row)

            print(
                case_id,
                label,
                f"G3_recovery={row['G3_natural_recovery']}",
                f"G4_trigger={row['G4_trigger']}",
                f"request_changed={row['request_changed']}",
                f"actions_changed={row['actions_changed']}",
                flush=True,
            )

    require(
        len(rows) == 6,
        "Expected six relation case-state configurations",
    )

    summary = {
        "status": "PASS",
        "classification": "read_only_planning_sensitivity",
        "configurations": len(rows),
        "G3_natural_recovery_count": sum(
            r["G3_natural_recovery"] for r in rows
        ),
        "G4_recovery_count": sum(
            r["G4_recovery"] for r in rows
        ),
        "G4_defer_count": sum(
            r["G4_trigger"] == "DEFER" for r in rows
        ),
        "request_changed_count": sum(
            r["request_changed"] for r in rows
        ),
        "actions_changed_count": sum(
            r["actions_changed"] for r in rows
        ),
        "rows": rows,
        "source_sha256": sources,
        "new_unity_calls": 0,
        "new_llm_calls": 0,
        "interpretation_rule": (
            "A changed prompt/request does not establish "
            "a changed action sequence or improved recovery."
        ),
    }

    OUT.mkdir(parents=True, exist_ok=False)

    (OUT / "gate.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    print()
    print("E6-2B RELATION PLANNING GATE: PASS")
    print(
        "G3 natural recoveries:",
        summary["G3_natural_recovery_count"], "/6"
    )
    print(
        "G4 DEFER recoveries:",
        summary["G4_defer_count"], "/6"
    )
    print(
        "Action sequence changes:",
        summary["actions_changed_count"], "/6"
    )
    print("New Unity calls: 0")
    print("New LLM calls: 0")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
