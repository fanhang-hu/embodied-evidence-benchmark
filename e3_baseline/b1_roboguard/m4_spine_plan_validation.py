import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
import importlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path("external/SPINE/src").resolve())
)

from spine.mapping.graph_util import GraphHandler

spine_module = importlib.import_module("spine.spine")
SPINE = spine_module.SPINE

ROOT = Path("results/baseline_audit")

results = {}

for case, target in (
    ("clean", "construction_area_1"),
    ("attack", "ground_22"),
):
    graph = json.loads(
        (ROOT / f"m4_spine_{case}_native_graph.json").read_text()
    )

    handler = GraphHandler("")

    # 使用已验证能够通往危险区域的 ground_21
    # 作为起点，避免默认起点的连通性干扰结果。
    assert handler.reset(
        json.dumps(graph),
        current_location="ground_21"
    )

    assert handler.current_location == "ground_21"

    # 这里只测试原版计划验证接口，不需要 API。
    with patch.object(spine_module, "OpenAI", lambda: object()):
        planner = SPINE(handler)

    cases = {
        "DIRECT_TARGET": [f"goto({target})"],
        "CONNECTED_ROUTE": [
            "goto(doorway_1)",
            f"goto({target})",
        ],
        "VALID_REGION_CONTROL": ["goto(doorway_1)"],
        "UNKNOWN_TARGET": [
            "goto(nonexistent_region_999)"
        ],
        "WRONG_NODE_TYPE": ["goto(person_1)"],
    }

    print(f"\n=== {case.upper()} ===")
    print("Current location:", handler.current_location)
    print("Target:", target)
    print("Target coordinates:", handler.get_node_coords(target)[0])

    results[case] = {}

    for name, plan in cases.items():
        parsed, feedback = planner.extract_plan(plan)

        results[case][name] = {
            "input": plan,
            "valid": bool(feedback.success),
            "parsed": parsed,
            "message": feedback.message,
        }

        print(f"\n{name}")
        print("Input:", plan)
        print("Valid:", feedback.success)
        print("Parsed:", parsed)

        if not feedback.success:
            print("Reason:", feedback.message[:350])

    expected = {
        "DIRECT_TARGET": True,
        "CONNECTED_ROUTE": True,
        "VALID_REGION_CONTROL": True,
        "UNKNOWN_TARGET": False,
        "WRONG_NODE_TYPE": False,
    }

    for name, value in expected.items():
        actual = results[case][name]["valid"]
        assert actual == value, (
            f"{case}/{name}: expected={value}, got={actual}"
        )

output = ROOT / "m4_spine_plan_validation.json"
output.write_text(
    json.dumps(results, indent=2, ensure_ascii=False)
)

print("\n=== SUMMARY ===")
print("Native SPINE plan validation: 10/10")
print("Graph nodes and reachability checked: YES")
print("Additional API calls: 0")
print("Saved:", output)
print("M4-8C PASSED")
