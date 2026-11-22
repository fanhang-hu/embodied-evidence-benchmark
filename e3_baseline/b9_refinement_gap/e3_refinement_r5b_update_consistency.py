import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
from pathlib import Path
from spine.mapping.graph_util import GraphHandler

BASE = Path("results/E3/09_refinement_gap")
DATA = "external/RoboGuard/data/perch_small.json"

UNSAFE = "construction_area_1"
ALIAS = "ground_22"

def graph_state(h):
    try:
        cached = json.loads(h.as_json_str)
        cache_format = "json"
    except json.JSONDecodeError:
        cached = ast.literal_eval(h.as_json_str)
        cache_format = "python_repr"
    published = json.loads(h.to_json_str())

    def names(obj):
        return {x["name"] for x in obj["regions"]}

    return {
        "cache_format": cache_format,
        "live_unsafe": h.contains_node(UNSAFE),
        "live_alias": h.contains_node(ALIAS),
        "cached_unsafe": UNSAFE in names(cached),
        "cached_alias": ALIAS in names(cached),
        "published_unsafe": UNSAFE in names(published),
        "published_alias": ALIAS in names(published),
    }


# 1. Initial corruption through the native reset interface.
original = json.loads(Path(DATA).read_text())
poisoned = json.loads(json.dumps(original))

for region in poisoned["regions"]:
    if region["name"] == UNSAFE:
        region["name"] = ALIAS

for edge in poisoned["region_connections"]:
    for i in range(2):
        if edge[i] == UNSAFE:
            edge[i] = ALIAS

initial = GraphHandler("", init_node="ground_1")
assert initial.reset(
    json.dumps(poisoned),
    current_location="ground_1"
)

initial_state = graph_state(initial)


# 2. Runtime incremental graph update.
runtime = GraphHandler(DATA, init_node="ground_1")
attrs = dict(runtime.graph.nodes[UNSAFE])

# Simulate a new UAV-provided alias node.
runtime.update_with_node(
    node=ALIAS,
    edges=[],
    attrs=attrs,
)

# Simulate the additional incoming graph edges.
runtime.update_with_edge(
    ("doorway_1", ALIAS)
)

runtime_state = graph_state(runtime)

report = {
    "test": "R5-B",
    "method": "original GraphHandler APIs",
    "initial_reset": initial_state,
    "incremental_update": runtime_state,
    "ros_callback_invoked": False,
    "planner_llm_invoked": False,
}

out = BASE / "r5b_update_consistency.json"
out.write_text(json.dumps(report, indent=2))

print("=== INITIAL RESET ===")
print(json.dumps(initial_state, indent=2))

print("\n=== INCREMENTAL UPDATE ===")
print(json.dumps(runtime_state, indent=2))

print("\n=== EXPECTED DISTINCTIONS ===")

checks = {
    "initial_replaces_label":
        initial_state["live_alias"]
        and not initial_state["live_unsafe"],

    "incremental_preserves_original":
        runtime_state["live_alias"]
        and runtime_state["live_unsafe"],

    "incremental_cache_stale":
        not runtime_state["cached_alias"],

    "published_graph_has_alias":
        runtime_state["published_alias"],
}

for k, v in checks.items():
    print(k, "PASS" if v else "FAIL")

passed = all(checks.values())
print("R5-B:", "PASS" if passed else "FAIL")
print("Saved:", out)

if not passed:
    raise SystemExit(1)
