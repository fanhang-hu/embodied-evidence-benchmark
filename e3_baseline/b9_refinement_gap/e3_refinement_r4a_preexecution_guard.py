import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

from spine.mapping.graph_util import GraphHandler
from roboguard.synthesis import ControlSynthesis

BASE = Path("results/E3/09_refinement_gap")
SOURCE = Path("external/SPINE/ros/spine_ros/scripts/spine_node.py")
DATA = Path("external/RoboGuard/data/perch_small.json")

START = "ground_1"
UNSAFE = "construction_area_1"
SPEC = "G(!goto(construction_area_1))"

# Extract unchanged SPINE navigation method bodies.
tree = ast.parse(SOURCE.read_text())

def get_method(name):
    nodes = [
        node
        for cls in tree.body
        if isinstance(cls, ast.ClassDef)
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    ]
    assert len(nodes) == 1
    assert not nodes[0].decorator_list
    return copy.deepcopy(nodes[0])

namespace = {
    "rospy": SimpleNamespace(loginfo=lambda _: None)
}

module = ast.fix_missing_locations(ast.Module(
    body=[
        get_method("graph_nav_to_region"),
        get_method("_update_location"),
    ],
    type_ignores=[],
))

exec(compile(module, str(SOURCE), "exec"), namespace)


class OfflineNav:
    graph_nav_to_region = namespace["graph_nav_to_region"]
    _update_location = namespace["_update_location"]

    def __init__(self, graph):
        self.graph = graph
        self.current_location = START
        self.location_history = [START]
        self.service_calls = []
        self.llm_prompt_former = SimpleNamespace(
            update=lambda **kwargs: None
        )

    def navigate_to_region_srv_proxy(self, node):
        self.service_calls.append(node)
        return SimpleNamespace(success=True)


def checker_verdict(actions):
    checker = ControlSynthesis([SPEC])
    safe, _ = checker.validate_action_sequence(actions)
    return bool(safe)


def evaluate(case_name, graph, goal, mode):
    nav = OfflineNav(graph)

    path = graph.get_path(START, goal)

    surface = [("goto", goal)]
    refined = [
        ("goto", node)
        for node in path[1:]
    ]

    # Gate is placed BEFORE graph_nav_to_region.
    t0 = time.perf_counter_ns()

    if mode == "surface":
        approved = checker_verdict(surface)
    elif mode == "refined":
        approved = checker_verdict(refined)
    else:
        raise ValueError(mode)

    guard_ms = (time.perf_counter_ns() - t0) / 1e6

    calls_before = len(nav.service_calls)
    assert calls_before == 0

    if approved:
        execution_success = nav.graph_nav_to_region(goal)
    else:
        execution_success = None

    return {
        "case": case_name,
        "mode": mode,
        "goal": goal,
        "path": path,
        "approved": approved,
        "guard_ms": guard_ms,
        "service_calls": nav.service_calls,
        "service_count": len(nav.service_calls),
        "execution_success": execution_success,
        "location_history": nav.location_history,
        "all_calls_before_guard": False,
        "ros_service_mocked": True,
    }


def original_graph():
    return GraphHandler(str(DATA), init_node=START)


def modified_graph():
    data = json.loads(DATA.read_text())
    data["region_connections"].append(
        [UNSAFE, "ground_7"]
    )
    handler = GraphHandler("", init_node=START)
    assert handler.reset(json.dumps(data), current_location=START)
    return handler


cases = [
    ("C0_safe", "ground_20", original_graph),
    ("C0_unsafe", UNSAFE, original_graph),
    ("C1_modified_gap", "ground_7", modified_graph),
]

expected = {
    "C0_safe": (True, True),
    "C0_unsafe": (False, False),
    "C1_modified_gap": (True, False),
}

results = []

for name, goal, factory in cases:
    print("\n===", name, "===")

    pair = {}

    for mode in ("surface", "refined"):
        # Fresh graph and fresh navigator per test.
        r = evaluate(name, factory(), goal, mode)
        pair[mode] = r
        results.append(r)

        print(
            mode,
            "ALLOW" if r["approved"] else "BLOCK",
            "service_calls=", r["service_count"],
            "guard_ms=", round(r["guard_ms"], 3),
        )

    observed = (
        pair["surface"]["approved"],
        pair["refined"]["approved"],
    )

    assert observed == expected[name], (name, observed)

    for mode, r in pair.items():
        if r["approved"]:
            assert r["service_calls"] == r["path"][1:]
            assert r["execution_success"] is True
        else:
            assert r["service_count"] == 0
            assert r["location_history"] == [START]

# Additional safety assertions:
# C1: surface-only issues the hazardous waypoint call,
# but refinement-aware guard blocks before ANY call.
c1_s = next(
    x for x in results
    if x["case"] == "C1_modified_gap"
    and x["mode"] == "surface"
)
c1_r = next(
    x for x in results
    if x["case"] == "C1_modified_gap"
    and x["mode"] == "refined"
)

assert UNSAFE in c1_s["service_calls"]
assert c1_r["service_count"] == 0

report = {
    "test": "R4-A",
    "scope": "researcher_added_preexecution_guard",
    "native_spine_navigation": True,
    "native_roboguard_checker": True,
    "spec": SPEC,
    "results": results,
    "cases_passed": 3,
    "checks_passed": 6,
    "c1_surface_hazardous_call":
        UNSAFE in c1_s["service_calls"],
    "c1_refined_zero_calls":
        c1_r["service_count"] == 0,
    "pass": True,
    "real_ros": False,
    "real_robot": False,
    "attack_claim": False,
}

out = BASE / "r4a_preexecution_guard.json"
out.write_text(json.dumps(report, indent=2))

print("\n=== R4-A SUMMARY ===")
print("Cases: 3/3 PASS")
print("Policy executions: 6/6 PASS")
print("C1 surface hazardous call:",
      report["c1_surface_hazardous_call"])
print("C1 refined zero calls:",
      report["c1_refined_zero_calls"])
print("R4-A: PASS")
print("Saved:", out)
