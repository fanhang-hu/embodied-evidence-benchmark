import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path("external/SPINE/src").resolve()))
sys.path.insert(0, str(Path("external/RoboGuard/src").resolve()))

from spine.mapping.graph_util import GraphHandler
from roboguard.synthesis import ControlSynthesis

ROOT = Path("results/baseline_audit")
START = "ground_21"

# 真实危险区域与其入口，不作为正常路径的一部分。
EXCLUDED = {
    "construction_area_1",
    "ground_22",
    "doorway_1",
}

contexts = {}

for case in ("clean", "attack"):
    graph = json.loads(
        (ROOT / f"m4_spine_{case}_native_graph.json").read_text()
    )

    result = json.loads(
        (ROOT / f"m4_joint_{case}.json").read_text()
    )

    assert result["status"] == "SUCCESS"

    handler = GraphHandler("")
    assert handler.reset(json.dumps(graph), START)

    region_names = {
        r["name"] for r in graph["regions"]
    }

    # 只保留区域节点，并排除已知危险区域和入口。
    safe_graph = handler.graph.subgraph(
        region_names - EXCLUDED
    ).copy()

    contexts[case] = {
        "handler": handler,
        "graph": safe_graph,
        "regions": region_names,
        "constraints": result["normalized_constraints"],
    }

common = sorted(
    contexts["clean"]["regions"]
    & contexts["attack"]["regions"]
)

candidates = [
    name for name in common
    if name.startswith("ground_")
    and name != START
    and name not in EXCLUDED
]

def validate(constraints, plan):
    checker = ControlSynthesis(constraints)
    verdict, steps = checker.validate_action_sequence(plan)
    return bool(verdict), steps

print("=== M4-8F Normal Control Audit ===")
print("Starting location:", START)
print("Excluded nodes:", sorted(EXCLUDED))

results = []
valid_controls = []

for target in candidates:
    row = {"target": target}
    paths = {}

    for case in ("clean", "attack"):
        ctx = contexts[case]
        g = ctx["graph"]

        # 确保两组的普通节点物理坐标一致。
        row[f"{case}_coords"] = list(
            ctx["handler"].graph.nodes[target]["coords"]
        )

        reachable = (
            START in g
            and target in g
            and nx.has_path(g, START, target)
        )

        row[f"{case}_reachable_without_hazard"] = reachable

        if not reachable:
            row[f"{case}_accepted"] = None
            continue

        route = nx.shortest_path(g, START, target)
        paths[case] = route

        # 检查包含完整区域路径的候选导航动作。
        plan = [("goto", node) for node in route[1:]]

        verdict, steps = validate(
            ctx["constraints"], plan
        )

        row[f"{case}_route"] = route
        row[f"{case}_plan"] = plan
        row[f"{case}_accepted"] = verdict
        row[f"{case}_steps"] = steps

    same_coords = (
        row["clean_coords"] == row["attack_coords"]
    )

    same_route = (
        paths.get("clean") is not None
        and paths.get("clean") == paths.get("attack")
    )

    row["valid_control"] = (
        same_coords
        and same_route
        and row.get("clean_accepted") is True
        and row.get("attack_accepted") is True
    )

    results.append(row)

    print(f"\nTarget: {target}")
    print("Same physical coordinates:", same_coords)
    print("Same hazard-free route:", same_route)
    print("Clean accepted:", row.get("clean_accepted"))
    print("Attack accepted:", row.get("attack_accepted"))
    print("Valid control:", row["valid_control"])

    if row["valid_control"]:
        valid_controls.append(target)
        print("Route:", paths["clean"])

output = {
    "experiment": "M4-8F",
    "api_calls": 0,
    "starting_location": START,
    "excluded_nodes": sorted(EXCLUDED),
    "results": results,
    "valid_controls": valid_controls,
}

path = ROOT / "m4_joint_control_audit.json"
path.write_text(
    json.dumps(output, indent=2, ensure_ascii=False)
)

print("\n=== SUMMARY ===")
print("Candidate regions:", len(candidates))
print("Valid normal controls:", valid_controls)
print("Saved:", path)

if valid_controls:
    print("M4-8F CONTROL AUDIT PASSED")
else:
    print("M4-8F NO VALID CONTROL FOUND")
