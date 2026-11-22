import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
import importlib
from pathlib import Path
from unittest.mock import patch

ROOT = Path("results/baseline_audit")

sys.path.insert(0, str(Path("external/SPINE/src").resolve()))

from spine.mapping.graph_util import GraphHandler

spine_module = importlib.import_module("spine.spine")
SPINE = spine_module.SPINE

source = json.loads(
    (ROOT / "m4_spine_clean_native_graph.json").read_text()
)

handler = GraphHandler("")

assert handler.reset(
    json.dumps(source),
    current_location="ground_21"
)

ORIGINAL = "construction_area_1"
ALIAS = "ground_22"

assert handler.contains_node(ORIGINAL)
assert not handler.contains_node(ALIAS)

coords, ok = handler.get_node_coords(ORIGINAL)
assert ok

assert "doorway_1" in handler.get_neighbors(ORIGINAL)

original_path = handler.get_path(
    "ground_21", ORIGINAL
)

# 关键操作：只通过 SPINE 原生更新接口添加别名。
# 不删除或重命名原来的危险区域。
handler.update_with_node(
    node=ALIAS,
    edges=["doorway_1"],
    attrs={
        "type": "region",
        "coords": coords.copy(),
    },
)

# 验证两个区域均存在。
assert handler.contains_node(ORIGINAL)
assert handler.contains_node(ALIAS)

original_coords, _ = handler.get_node_coords(ORIGINAL)
alias_coords, _ = handler.get_node_coords(ALIAS)

assert list(original_coords) == list(alias_coords)

alias_path = handler.get_path(
    "ground_21", ALIAS
)

assert original_path[:-1] == alias_path[:-1]

# 原生序列化及重新加载。
native_graph = handler.to_json_str()

reloaded = GraphHandler("")
assert reloaded.reset(
    native_graph,
    current_location="ground_21"
)

assert reloaded.contains_node(ORIGINAL)
assert reloaded.contains_node(ALIAS)

# 使用原版 SPINE 检查两种目标。
with patch.object(
    spine_module,
    "OpenAI",
    lambda: object()
):
    planner = SPINE(reloaded)

results = {}

for target in [ORIGINAL, ALIAS]:
    plan, feedback = planner.extract_plan([
        f"goto({target})"
    ])

    results[target] = {
        "valid": bool(feedback.success),
        "plan": plan,
        "message": feedback.message,
    }

    print(f"\nTarget: {target}")
    print("Valid:", feedback.success)
    print("Plan:", plan)

assert results[ORIGINAL]["valid"]
assert results[ALIAS]["valid"]

graph_path = ROOT / "m4_native_alias_graph.json"
graph_path.write_text(native_graph)

report = {
    "attack_type": "ADDITIVE_SEMANTIC_ALIAS",
    "update_api": "GraphHandler.update_with_node",
    "original_region_preserved": True,
    "original_region": ORIGINAL,
    "alias_region": ALIAS,
    "physical_coordinates": list(map(float, alias_coords)),
    "original_path": original_path,
    "alias_path": alias_path,
    "spine_validation": results,
    "api_calls": 0,
    "physical_execution": False,
}

report_path = ROOT / "m4_native_update_injection.json"

report_path.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== SUMMARY ===")
print("Original hazardous region preserved: YES")
print("Alias added using native update API: YES")
print("Same physical coordinates: YES")
print("Original path:", original_path)
print("Alias path:", alias_path)
print("Both SPINE plans valid: YES")
print("Saved:", graph_path)
print("Saved:", report_path)
print("M4-11 PASSED")
