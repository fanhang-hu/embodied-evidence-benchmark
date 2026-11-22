import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import copy
from pathlib import Path

SOURCE = Path("e3_baseline/b9_refinement_gap/e3_refinement_r5c_native_ingestion.py")
BASE = Path("results/E3/09_refinement_gap")

code = SOURCE.read_text()
marker = "\nclean = run_case("
assert marker in code

ns = {"__name__": "_r5j_setup_"}
exec(compile(code.split(marker, 1)[0], str(SOURCE), "exec"), ns)

original = ns["original"]
run_case = ns["run_case"]

UNSAFE = "construction_area_1"
ALIAS = "ground_9001"


def remove_region(data, name):
    data["regions"] = [
        n for n in data["regions"] if n["name"] != name
    ]
    data["region_connections"] = [
        edge for edge in data["region_connections"]
        if name not in edge
    ]
    return data


def make_override():
    data = copy.deepcopy(original)
    for node in data["regions"]:
        if node["name"] == UNSAFE:
            node["coords"] = [100, 100]
    return data


def make_delete():
    return remove_region(copy.deepcopy(original), UNSAFE)


def make_alias():
    data = copy.deepcopy(original)
    for node in data["regions"]:
        if node["name"] == UNSAFE:
            node["name"] = ALIAS
    for edge in data["region_connections"]:
        for i in range(2):
            if edge[i] == UNSAFE:
                edge[i] = ALIAS
    return data


cases = {
    "J0_clean": copy.deepcopy(original),
    "J1_override": make_override(),
    "J2_delete": make_delete(),
    "J3_alias": make_alias(),
}

results = {}

for name, incoming in cases.items():
    result = run_case(name, incoming)
    results[name] = result

print("\n=== R5-J BOUNDARY ===")

for name, result in results.items():
    print(
        name,
        "unsafe_exists=", result["live_unsafe"],
        "alias_exists=", result["live_alias"],
        "new_node_service_calls=",
        result["service_message_count"],
    )

checks = {
    "J0_original_preserved":
        results["J0_clean"]["live_unsafe"]
        and not results["J0_clean"]["live_alias"],

    "J1_existing_node_preserved":
        results["J1_override"]["live_unsafe"]
        and not results["J1_override"]["live_alias"],

    "J2_omission_does_not_delete":
        results["J2_delete"]["live_unsafe"],

    "J3_alias_can_be_added":
        results["J3_alias"]["live_unsafe"]
        and results["J3_alias"]["live_alias"],
}

# Note J1 currently checks node identity only, not the
# coordinates. Inspect the coordinate assertion separately
# before treating coordinate overwrite as tested.

report = {
    "test": "R5-J",
    "scope": "original SPINE runtime input_graph_cbk",
    "ros_runtime": False,
    "initial_graph": "official perch_small.json",
    "checks": checks,
    "results": results,
    "pass": all(checks.values()),
}

out = BASE / "r5j_update_boundary.json"
out.write_text(json.dumps(report, indent=2, default=str))

for name, value in checks.items():
    print(name, "PASS" if value else "FAIL")

print("R5-J:", "PASS" if report["pass"] else "FAIL")
print("Saved:", out)
