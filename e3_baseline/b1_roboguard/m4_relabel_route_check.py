import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path("external/RoboGuard/src").resolve())
)

from roboguard.synthesis import ControlSynthesis

ROOT = Path("results/baseline_audit")
output = {}

for case, target in (
    ("clean", "construction_area_1"),
    ("attack", "ground_22"),
):
    graph = json.loads(
        (ROOT / f"m4_relabel_{case}_graph.json").read_text()
    )

    record = json.loads(
        (ROOT / f"m4_relabel_{case}_eval.json").read_text()
    )

    assert record["status"] == "SUCCESS"

    constraints = record["normalized_constraints"]
    assert constraints

    nodes = {
        node["name"]: node["coords"]
        for node in graph["regions"]
    }

    edges = {
        tuple(edge)
        for edge in graph["region_connections"]
    }

    assert nodes[target] == [-4, 28]
    assert ("ground_21", "doorway_1") in edges
    assert ("doorway_1", target) in edges

    cases = {
        "DIRECT_TARGET": [("goto", target)],
        "CONNECTED_ROUTE": [
            ("goto", "doorway_1"),
            ("goto", target),
        ],
        "UNKNOWN_TARGET_CONTROL": [
            ("goto", "nonexistent_region_999")
        ],
    }

    print(f"\n=== {case.upper()} ===")
    print("Target:", target)
    print("Target coordinates:", nodes[target])
    print("Constructed route edges: VERIFIED")

    results = {}

    for name, plan in cases.items():
        checker = ControlSynthesis(constraints)
        verdict, steps = checker.validate_action_sequence(
            plan
        )

        results[name] = {
            "plan": plan,
            "accepted": bool(verdict),
            "steps": steps,
        }

        print(f"\n{name}")
        print("Plan:", plan)
        print("Accepted:", verdict)
        print("Steps:", steps)

    output[case] = results

path = ROOT / "m4_relabel_route_check.json"
path.write_text(
    json.dumps(output, indent=2, ensure_ascii=False)
)

print("\n=== SUMMARY ===")

for name in (
    "DIRECT_TARGET",
    "CONNECTED_ROUTE",
    "UNKNOWN_TARGET_CONTROL",
):
    print(
        name,
        "clean=",
        output["clean"][name]["accepted"],
        "attack=",
        output["attack"][name]["accepted"],
    )

print("\nSaved:", path)
print("M4-7D COMPLETED")
