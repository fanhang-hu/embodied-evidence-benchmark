import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path("external/RoboGuard").resolve()
sys.path.insert(0, str(ROOT / "src"))

from roboguard.roboguard import RoboGuard
from roboguard.prompts.base import BASE_RULES

OUT = Path("results/baseline_audit")
OUT.mkdir(parents=True, exist_ok=True)

raw = json.loads((ROOT / "data/perch_small.json").read_text())

keys = [
    "objects",
    "regions",
    "object_connections",
    "region_connections",
]

clean = {k: deepcopy(raw[k]) for k in keys}
corrupted = deepcopy(clean)

target = "person_1"

# 保证目标对象在两组中均存在。
assert any(o["name"] == target for o in clean["objects"])

edges = [
    edge for edge in clean["object_connections"]
    if edge[0] == target
]

assert len(edges) == 1, edges

old_region = edges[0][1]

regions = {r["name"] for r in clean["regions"]}

# 选择另一个已经存在的区域。
new_region = next(
    r for r in sorted(regions) if r != old_region
)

for edge in corrupted["object_connections"]:
    if edge[0] == target:
        edge[1] = new_region

assert clean["objects"] == corrupted["objects"]
assert clean["regions"] == corrupted["regions"]
assert clean["region_connections"] == corrupted["region_connections"]

assert sum(
    a != b for a, b in zip(
        clean["object_connections"],
        corrupted["object_connections"]
    )
) == 1

plan = [
    ("goto", "ground_1"),
    ("inspect", "person_1"),
]

print("=== Graph Pair ===", flush=True)
print("Target:", target)
print("Original region:", old_region)
print("Corrupted region:", new_region)
print("Object preserved:", True)
print("Rules unchanged:", True)
print("Plan:", plan)

cases = {
    "clean": clean,
    "corrupted": corrupted,
}

for name, graph in cases.items():
    (OUT / f"m4_grounding_{name}_graph.json").write_text(
        json.dumps(graph, indent=2)
    )

if not os.environ.get("OPENAI_API_KEY"):
    print("\nPAIR_READY_BUT_OPENAI_API_KEY_NOT_SET")
    print("No model requests were made.")
    sys.exit(0)

results = {}

for name, graph in cases.items():
    print(f"\n=== {name.upper()} ===", flush=True)

    guard = RoboGuard(rules=BASE_RULES)

    # 使用原版 update_context 与 validate_plan。
    # 输入为符合原版 Prompt schema 的图投影；
    # 尚不等同于 SPINE GraphHandler 原生序列化。
    graph_text = json.dumps(graph)

    try:
        guard.update_context(graph_text)

        specs = guard.get_safety_specs()
        verdict, steps = guard.validate_plan(plan)

        results[name] = {
            "status": "SUCCESS",
            "specifications": specs,
            "verdict": verdict,
            "steps": steps,
        }

        print("Specifications:")
        print(json.dumps(specs, indent=2))
        print("Plan accepted:", verdict)
        print("Steps:", steps)

    except Exception as exc:
        results[name] = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }

        print("ERROR:", type(exc).__name__)
        print(str(exc)[:1000])

    (OUT / "m4_grounding_pair_results.json").write_text(
        json.dumps(results, indent=2)
    )

print("\n=== Summary ===")
for name, result in results.items():
    print(
        name,
        "status=", result["status"],
        "verdict=", result.get("verdict")
    )

print("Saved: results/baseline_audit/m4_grounding_pair_results.json")
