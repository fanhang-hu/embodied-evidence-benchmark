import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
from pathlib import Path

ROOT = Path("results/baseline_audit")

def load(name):
    return json.loads((ROOT / name).read_text())

def coord(value):
    if isinstance(value, str):
        value = ast.literal_eval(value)
    return tuple(round(float(v), 4) for v in value)

trusted = load("m4_spine_clean_native_graph.json")

# 可信快照：坐标 -> 原始区域身份
trusted_index = {}

for node in trusted["regions"]:
    key = coord(node["coords"])
    trusted_index.setdefault(key, []).append(node["name"])

def verify_plan(plan, current_graph):
    current = {
        node["name"]: coord(node["coords"])
        for node in current_graph["regions"]
    }

    evidence = []

    for action, target in plan:
        if action != "goto":
            return "DEFER", evidence

        if target not in current:
            return "DEFER", evidence

        position = current[target]
        matches = trusted_index.get(position, [])

        matched = (
            len(matches) == 1
            and matches[0] == target
        )

        evidence.append({
            "target": target,
            "coordinates": position,
            "trusted_names": matches,
            "identity_matches": matched,
        })

        if not matched:
            return "DEFER", evidence

    return "PASS", evidence

def fuse(baseline_accepted, verification):
    if not baseline_accepted:
        return "BLOCK"

    if verification == "PASS":
        return "ALLOW"

    return "DEFER"

audit = load("m4_joint_control_audit.json")
normal_plans = {
    row["target"]: [tuple(x) for x in row["clean_plan"]]
    for row in audit["results"]
    if row["target"] in audit["valid_controls"]
}
assert len(normal_plans) == 9

report = {}

for run, prefix in (
    ("original", "m4_joint"),
    ("repeat01", "m4_joint_repeat01"),
):
    report[run] = {}

    for case in ("clean", "attack"):
        record = load(f"{prefix}_{case}.json")
        graph = load(f"m4_spine_{case}_native_graph.json")

        assert record["status"] == "SUCCESS"

        target_plan = [tuple(x) for x in record["plan"]]
        verification, evidence = verify_plan(target_plan, graph)

        baseline = record["accepted"]
        final = fuse(baseline, verification)

        normal_results = []

        for target, plan in normal_plans.items():
            # 使用此前保存的真实 RoboGuard 约束
            from sys import path
            from pathlib import Path as P
            repo = str(P("external/RoboGuard/src").resolve())
            if repo not in path:
                path.insert(0, repo)

            from roboguard.synthesis import ControlSynthesis

            checker = ControlSynthesis(
                record["normalized_constraints"]
            )
            allowed, _ = checker.validate_action_sequence(plan)

            check, _ = verify_plan(plan, graph)
            decision = fuse(bool(allowed), check)

            normal_results.append({
                "target": target,
                "decision": decision,
            })

        passed = sum(
            x["decision"] == "ALLOW"
            for x in normal_results
        )

        report[run][case] = {
            "baseline": "ALLOW" if baseline else "BLOCK",
            "snapshot_check": verification,
            "combined": final,
            "target_evidence": evidence,
            "normal_allowed": passed,
            "normal_total": len(normal_results),
            "normal_results": normal_results,
        }

        print(f"\n=== {run.upper()} / {case.upper()} ===")
        print("RoboGuard:", "ALLOW" if baseline else "BLOCK")
        print("Snapshot verification:", verification)
        print("Combined:", final)
        print("Normal paths:", f"{passed}/9")

        for item in evidence:
            if not item["identity_matches"]:
                print("Mismatch:", item)

output = ROOT / "m4_trusted_snapshot_defense.json"
output.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== SUMMARY ===")
print("Defense: TRUSTED_MAP_SNAPSHOT")
print("Additional API calls: 0")
print("Physical execution: NO")
print("Saved:", output)
print("E2-M2 COMPLETED")
