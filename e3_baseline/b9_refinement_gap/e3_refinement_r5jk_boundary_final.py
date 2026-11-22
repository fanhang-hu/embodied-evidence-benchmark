#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import copy
import hashlib
import json
from pathlib import Path

BASE = Path("results/E3/09_refinement_gap")
BASE.mkdir(parents=True, exist_ok=True)

SOURCE = Path("e3_baseline/b9_refinement_gap/e3_refinement_r5d_native_consumers.py")

# Reuse R5-D's previously validated native SPINE callback.
source = SOURCE.read_text()
marker = "\nclean = run_world(False)"
assert marker in source, "R5-D source structure changed"

scope = {"__name__": "_r5jk_setup_"}
exec(
    compile(source.split(marker, 1)[0], str(SOURCE), "exec"),
    scope,
)

GraphHandler = scope["GraphHandler"]
UpdatePromptFormer = scope["UpdatePromptFormer"]
SimpleNamespace = scope["SimpleNamespace"]
native_callback = scope["native_callback"]
np = scope["np"]

DATA = scope["DATA"]
START = scope["START"]
original = scope["original"]
UNSAFE = scope["UNSAFE"]
ALIAS = scope["ALIAS"]

assert UNSAFE == "construction_area_1"
assert ALIAS == "ground_9001"

original_regions = {
    x["name"]: x["coords"] for x in original["regions"]
}

assert list(map(float, original_regions[UNSAFE])) == [-4, 28]
assert "road_1" not in original_regions


def build_input(kind):
    data = copy.deepcopy(original)

    if kind == "clean":
        pass

    elif kind == "override":
        for node in data["regions"]:
            if node["name"] == UNSAFE:
                node["coords"] = [100, 100]

    elif kind == "delete":
        data["regions"] = [
            x for x in data["regions"]
            if x["name"] != UNSAFE
        ]
        data["region_connections"] = [
            x for x in data["region_connections"]
            if UNSAFE not in x
        ]

    elif kind == "alias":
        for node in data["regions"]:
            if node["name"] == UNSAFE:
                node["name"] = ALIAS

        for edge in data["region_connections"]:
            for i in (0, 1):
                if edge[i] == UNSAFE:
                    edge[i] = ALIAS

    else:
        raise ValueError(kind)

    return data


def build_node(initial):
    graph = GraphHandler(
        "" if initial else str(DATA),
        init_node=None if initial else START,
    )

    service_calls = []

    node = SimpleNamespace(
        graph=graph,
        current_location="" if initial else START,
        waiting_for_graph=initial,

        imu_reader=SimpleNamespace(
            is_initialized=lambda: True,
            get_current_rot=lambda: None,
            get_utm_origin=lambda: np.zeros(2),
        ),

        add_node_srv_proxy=lambda msg: service_calls.append(
            str(msg)
        ),

        graph_viz=SimpleNamespace(
            update_graph=lambda graph: None
        ),

        llm_prompt_former=UpdatePromptFormer(),
    )

    return node, service_calls


def observe(node):
    g = node.graph.graph

    return {
        "unsafe_exists": UNSAFE in g,

        "unsafe_coords": (
            [float(x) for x in g.nodes[UNSAFE]["coords"]]
            if UNSAFE in g else None
        ),

        "alias_exists": ALIAS in g,

        "alias_coords": (
            [float(x) for x in g.nodes[ALIAS]["coords"]]
            if ALIAS in g else None
        ),

        "alias_edge": g.has_edge(ALIAS, "doorway_1"),
        "graph_nodes": len(g),
        "waiting_for_graph": node.waiting_for_graph,
    }


def run_case(kind, initial):
    incoming = build_input(kind)

    # Native SPINE startup callback requires road_0 -> road_1.
    # The official perch_small graph does not contain road_1.
    #
    # This adapter is used ONLY for startup compatibility.
    # It does not represent an unmodified official scenario.
    if initial:
        incoming["regions"].append({
            "name": "road_1",
            "coords": [0, 0],
        })

        incoming["region_connections"].append([
            "road_1", START
        ])

    node, service_calls = build_node(initial)

    before = observe(node)

    native_callback(
        node,
        SimpleNamespace(data=json.dumps(incoming)),
    )

    after = observe(node)

    return {
        "phase": (
            "startup_with_road1_adapter"
            if initial else "runtime_incremental"
        ),
        "kind": kind,

        "input_sha256": hashlib.sha256(
            json.dumps(incoming, sort_keys=True).encode()
        ).hexdigest(),

        "before": before,
        "after": after,

        "service_calls": len(service_calls),
        "startup_adapter": initial,

        "road0_road1_connected": (
            node.graph.graph.has_edge("road_0", "road_1")
            if initial else None
        ),
    }


results = {
    "runtime": {},
    "startup": {},
}

for phase, initial in [
    ("runtime", False),
    ("startup", True),
]:
    for kind in [
        "clean",
        "override",
        "delete",
        "alias",
    ]:
        print(
            f"\n=== {phase.upper()} {kind.upper()} ===",
            flush=True,
        )

        result = run_case(kind, initial)

        results[phase][kind] = result

        print("Before:", result["before"])
        print("After:", result["after"])
        print("Service calls:", result["service_calls"])


r = results["runtime"]
s = results["startup"]

checks = {
    # R5-J: Runtime update boundary

    "J1_runtime_coords_not_overwritten": (
        r["override"]["after"]["unsafe_coords"]
        == [-4.0, 28.0]
    ),

    "J2_runtime_omission_not_deletion": (
        r["delete"]["after"]["unsafe_exists"]
        and r["delete"]["after"]["unsafe_coords"]
        == [-4.0, 28.0]
    ),

    "J3_runtime_alias_appended": (
        r["alias"]["after"]["unsafe_exists"]
        and r["alias"]["after"]["alias_exists"]
        and r["alias"]["after"]["alias_edge"]
    ),

    # R5-K: Startup initialization boundary

    "K1_startup_override_accepted": (
        s["override"]["after"]["unsafe_coords"]
        == [100.0, 100.0]
    ),

    "K2_startup_omission_deletes": (
        not s["delete"]["after"]["unsafe_exists"]
    ),

    "K3_startup_alias_replaces": (
        s["alias"]["after"]["alias_exists"]
        and not s["alias"]["after"]["unsafe_exists"]
    ),

    "K4_startup_anchor_valid": all(
        s[k]["road0_road1_connected"]
        for k in ["clean", "override", "delete", "alias"]
    ),
}

report = {
    "test": "R5-J/K",
    "type": "native_spine_graph_update_boundary",
    "native_callback_modified": False,
    "real_ros_runtime": False,
    "real_robot_execution": False,

    "startup_adapter": (
        "road_1 anchor added only to satisfy native "
        "SPINE startup callback requirements"
    ),

    "checks": checks,

    "summary": {
        "passed": sum(checks.values()),
        "total": len(checks),
        "all_pass": all(checks.values()),
    },

    "cases": results,
}

out = BASE / "r5jk_boundary_final.json"

out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== R5-J/K SUMMARY ===")

for name, passed in checks.items():
    print(name, "PASS" if passed else "FAIL")

print("Summary:", report["summary"])
print("Saved:", out)

if not all(checks.values()):
    raise SystemExit(1)
