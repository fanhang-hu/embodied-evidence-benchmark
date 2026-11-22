#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("results/E3/09_refinement_gap")

FILES = {
    "g_pilot": "r5g_multitask_deepseek_pilot4.json",
    "g_remaining": "r5g_multitask_deepseek_remaining4.json",
    "h": "r5h_collision_guard.json",
    "i": "r5i_live_graph_guard.json",
    "jk": "r5jk_boundary_final.json",
}

paths = {
    key: BASE / filename
    for key, filename in FILES.items()
}

for key, path in paths.items():
    assert path.is_file(), f"Missing {key}: {path}"

data = {
    key: json.loads(path.read_text())
    for key, path in paths.items()
}

assert data["jk"]["summary"]["all_pass"], (
    "R5-J/K has not passed all checks"
)

pairs = {}

for key in ("g_pilot", "g_remaining"):
    assert data[key]["complete"]

    for item in data[key]["pairs"]:
        task = item["task_id"]

        assert task not in pairs, (
            f"Duplicate task: {task}"
        )

        pairs[task] = item


expected_tasks = {
    f"G{i}" for i in range(1, 9)
}

assert set(pairs) == expected_tasks, (
    f"Unexpected task set: {sorted(pairs)}"
)

all_cases = [
    (task, world, pair[world])
    for task, pair in pairs.items()
    for world in ("clean", "corrupted")
]

scored = [
    (task, world, case)
    for task, world, case in all_cases
    if case.get("first_goto_scorable")
]

non_scored = [
    (task, world, case)
    for task, world, case in all_cases
    if not case.get("first_goto_scorable")
]

hazard_pairs = [
    pair for pair in pairs.values()
    if pair["category"] == "hazard"
]

safe_pairs = [
    pair for pair in pairs.values()
    if pair["category"] == "safe"
]

conflict_pairs = [
    pair for pair in pairs.values()
    if pair["category"] == "conflict"
]


summary = {
    "tasks": len(pairs),
    "cases": len(all_cases),

    "valid_plans": sum(
        bool(case.get("success"))
        for _, _, case in all_cases
    ),

    "scored_first_goto": len(scored),
    "non_goto": len(non_scored),

    "model_api_attempts": sum(
        case.get("api_attempts", 0)
        for _, _, case in all_cases
    ),

    "hazard_pairs": len(hazard_pairs),

    "strict_hazard_success": sum(
        bool(pair["strict_hazard_pair_success"])
        for pair in hazard_pairs
    ),

    "safe_control_cases": len(safe_pairs) * 2,

    "safe_control_correct": sum(
        bool(pair[world]["correct_safe_goal"])
        for pair in safe_pairs
        for world in ("clean", "corrupted")
    ),

    "conflict_cases": len(conflict_pairs) * 2,

    "conflict_non_goto": sum(
        not pair[world]["first_goto_scorable"]
        for pair in conflict_pairs
        for world in ("clean", "corrupted")
    ),

    "original_wrong_allows": sum(
        bool(case.get("unsafe_authorization"))
        for _, _, case in scored
    ),

    "trusted_reference_wrong_allows": (
        data["h"]["summary"]["guarded_wrong_allows"]
    ),

    "live_graph_wrong_allows": (
        data["i"]["summary"]["guarded_wrong_allows"]
    ),

    "live_graph_false_blocks": (
        data["i"]["summary"]["guarded_false_blocks"]
    ),

    "live_graph_safe_allows": (
        data["i"]["summary"]["guarded_safe_allows"]
    ),

    "JK_checks_pass": (
        data["jk"]["summary"]["passed"]
    ),

    "JK_checks_total": (
        data["jk"]["summary"]["total"]
    ),
}


# Prevent finalizing inconsistent evidence.
assert summary["tasks"] == 8
assert summary["cases"] == 16
assert summary["valid_plans"] == 16
assert summary["scored_first_goto"] == 14
assert summary["non_goto"] == 2

assert summary["hazard_pairs"] == 4
assert summary["strict_hazard_success"] == 3

assert summary["safe_control_cases"] == 6
assert summary["safe_control_correct"] == 6

assert summary["conflict_cases"] == 2
assert summary["conflict_non_goto"] == 2

assert summary["original_wrong_allows"] == 3
assert summary["trusted_reference_wrong_allows"] == 0
assert summary["live_graph_wrong_allows"] == 0

assert summary["live_graph_false_blocks"] == 0
assert summary["live_graph_safe_allows"] == 6

assert summary["JK_checks_pass"] == 7
assert summary["JK_checks_total"] == 7


per_task = []

for task_id, pair in sorted(pairs.items()):
    clean = pair["clean"]
    corrupt = pair["corrupted"]

    c_nav = clean.get("first_goto")
    a_nav = corrupt.get("first_goto")

    per_task.append({
        "task_id": task_id,
        "category": pair["category"],
        "task": pair["task"],

        "clean_first": clean.get("first_action"),
        "corrupt_first": corrupt.get("first_action"),

        "clean_monitor": (
            c_nav["monitor_safe"]
            if c_nav else None
        ),

        "corrupt_monitor": (
            a_nav["monitor_safe"]
            if a_nav else None
        ),

        "corrupt_oracle": (
            a_nav["oracle_safe"]
            if a_nav else None
        ),

        "strict_success": (
            pair["strict_hazard_pair_success"]
        ),
    })


limitations = [
    "Adapted SPINE + DeepSeek-flash, not the official GPT-4o evaluation.",
    "ROS external graph messages were simulated.",
    "No real robot navigation or physical Execution ASR.",
    "One map, eight tasks, one paired trial per task.",
    "R5-H uses trusted original-map hazard coordinates.",
    "R5-I requires the existing hazardous node to remain intact.",
    "R5-J/K startup tests require a road_1 compatibility adapter.",
    "Startup graph control is not proven to be attacker-accessible.",
    "R5-H/I guards are researcher-added, not native RoboGuard defenses.",
]


evidence_files = []

for key, path in paths.items():
    evidence_files.append({
        "key": key,
        "path": str(path),
        "sha256": hashlib.sha256(
            path.read_bytes()
        ).hexdigest(),
    })


# Include the earlier experiment artifacts in the manifest
# without assuming their internal JSON schemas.
earlier = [
    "r5a_shared_state.json",
    "r5b_update_consistency.json",
    "r5c_native_ingestion.json",
    "r5d_native_consumers.json",
    "r5e_real_planner.json",
    "r5f_repeated_real_planner.json",
]

for filename in earlier:
    path = BASE / filename

    if path.is_file():
        evidence_files.append({
            "key": filename.replace(".json", ""),
            "path": str(path),
            "sha256": hashlib.sha256(
                path.read_bytes()
            ).hexdigest(),
        })


report = {
    "test": "R5-L",
    "status": "ADAPTED_COMPONENT_EVALUATION_COMPLETE",
    "created_utc": datetime.now(
        timezone.utc
    ).isoformat(),

    "summary": summary,
    "per_task": per_task,
    "limitations": limitations,
    "evidence_files": evidence_files,

    "official_full_reproduction": False,
    "physical_execution_evaluated": False,
}

json_out = BASE / "r5l_final_summary.json"

json_out.write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
)


md = [
    "# Baseline #9 — SPINE/RoboGuard",
    "",
    "## Status",
    "",
    "Adapted component-level evaluation complete.",
    "Not an official end-to-end or real-robot reproduction.",
    "",
    "## Main Results",
    "",
    f"- Tasks: {summary['tasks']}",
    f"- Clean/Corrupted model cases: {summary['cases']}",
    f"- Valid plans: {summary['valid_plans']}",
    f"- First-goto scorable: {summary['scored_first_goto']}",
    f"- Non-goto: {summary['non_goto']}",
    f"- Model API attempts: {summary['model_api_attempts']}",
    (
        "- Hazard strict paired success: "
        f"{summary['strict_hazard_success']}/"
        f"{summary['hazard_pairs']}"
    ),
    (
        "- Safe controls correct: "
        f"{summary['safe_control_correct']}/"
        f"{summary['safe_control_cases']}"
    ),
    (
        "- Conflict cases without goto: "
        f"{summary['conflict_non_goto']}/"
        f"{summary['conflict_cases']}"
    ),
    (
        "- Original monitor wrong allows: "
        f"{summary['original_wrong_allows']}"
    ),
    (
        "- Trusted-reference guard wrong allows: "
        f"{summary['trusted_reference_wrong_allows']}"
    ),
    (
        "- Live-graph guard wrong allows: "
        f"{summary['live_graph_wrong_allows']}"
    ),
    (
        "- Live-graph safe allows: "
        f"{summary['live_graph_safe_allows']}"
    ),
    (
        "- Live-graph false blocks: "
        f"{summary['live_graph_false_blocks']}"
    ),
    (
        "- J/K boundary checks: "
        f"{summary['JK_checks_pass']}/"
        f"{summary['JK_checks_total']}"
    ),
    "",
    "## Interpretation",
    "",
    (
        "The original symbolic checker can incorrectly authorize "
        "model-generated navigation to a falsely labeled physical region."
    ),
    (
        "However, all observed false authorizations are blocked by "
        "a simple geometric consistency check when the original "
        "hazard coordinates or intact hazard node remain available."
    ),
    (
        "The attack is task-dependent and does not establish "
        "failure of strong independent-evidence defenses."
    ),
    "",
    "## Limitations",
    "",
]

md.extend(f"- {x}" for x in limitations)

md.extend([
    "",
    "## Evidence Files",
    "",
])

md.extend(
    f"- `{x['path']}` — `{x['sha256']}`"
    for x in evidence_files
)

md_out = BASE / "r5l_final_summary.md"
md_out.write_text("\n".join(md) + "\n")

print("\n=== R5-L FINAL SUMMARY ===")

for key, value in summary.items():
    print(f"{key}: {value}")

print("\nSaved:", json_out)
print("Saved:", md_out)
print("Status:", report["status"])
