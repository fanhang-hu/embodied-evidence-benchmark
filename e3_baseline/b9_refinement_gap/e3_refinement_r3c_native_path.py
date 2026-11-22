import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import copy
import hashlib
import networkx as nx
from pathlib import Path

from spine.mapping.graph_util import GraphHandler
from roboguard.synthesis import ControlSynthesis

BASE = Path("results/E3/09_refinement_gap")
DATA = Path("external/RoboGuard/data/perch_small.json")

START = "ground_1"
UNSAFE = "construction_area_1"
SPEC = "G(!goto(construction_area_1))"

raw = DATA.read_bytes()
source_hash = hashlib.sha256(raw).hexdigest()
data = json.loads(raw)


def verify(actions):
    checker = ControlSynthesis([SPEC])
    verdict, steps = checker.validate_action_sequence(
        actions
    )
    return {
        "safe": bool(verdict),
        "actions": actions,
        "steps": [
            [str(a), bool(s)]
            for a, s in steps
        ],
    }


def evaluate(handler, goal):
    # Exact original SPINE GraphHandler path API.
    path = handler.get_path(
        handler.current_location,
        goal,
    )

    # All traversed nodes must be real graph edges.
    assert all(
        handler.graph.has_edge(a, b)
        for a, b in zip(path, path[1:])
    )

    assert all(
        handler.graph.nodes[node]["type"] == "region"
        for node in path
    )

    surface = verify([("goto", goal)])

    refined = verify([
        ("goto", node)
        for node in path[1:]
    ])

    return {
        "goal": goal,
        "native_path": path,
        "surface": surface,
        "refined": refined,
        "gap": (
            surface["safe"]
            and not refined["safe"]
        ),
    }


print("=== C0: UNMODIFIED OFFICIAL GRAPH ===")

original = GraphHandler(
    str(DATA),
    init_node=START,
)

assert original.graph.number_of_nodes() == 25
assert original.graph.number_of_edges() == 22

c0_safe = evaluate(original, "ground_20")
c0_unsafe = evaluate(original, UNSAFE)

original_goal_reachable = nx.has_path(
    original.graph, START, "ground_7"
)

print("Safe target:", c0_safe["native_path"])
print(
    "Safe verdicts:",
    c0_safe["surface"]["safe"],
    c0_safe["refined"]["safe"],
)

print("Unsafe target:", c0_unsafe["native_path"])
print(
    "Unsafe verdicts:",
    c0_unsafe["surface"]["safe"],
    c0_unsafe["refined"]["safe"],
)

print(
    "ground_7 originally reachable:",
    original_goal_reachable,
)


print("\n=== C1: SINGLE-EDGE MODIFIED COPY ===")

modified_data = copy.deepcopy(data)

added_edge = [UNSAFE, "ground_7"]

assert added_edge not in (
    modified_data["region_connections"]
)

modified_data["region_connections"].append(
    added_edge
)

# Parse through original SPINE GraphHandler.
# Do not modify the repository dataset.
modified = GraphHandler("", init_node=START)

assert modified.reset(
    json.dumps(modified_data),
    current_location=START,
)

assert modified.graph.number_of_nodes() == 25
assert modified.graph.number_of_edges() == 23

c1_target = evaluate(modified, "ground_7")
c1_control = evaluate(modified, "ground_20")

print("Added edge:", added_edge)
print("Native path:", c1_target["native_path"])
print(
    "Surface SAFE:",
    c1_target["surface"]["safe"],
)
print(
    "Refined SAFE:",
    c1_target["refined"]["safe"],
)
print("Gap:", c1_target["gap"])

print(
    "Unchanged safe control:",
    c1_control["surface"]["safe"],
    c1_control["refined"]["safe"],
)

# Verify source file is unchanged.
assert hashlib.sha256(
    DATA.read_bytes()
).hexdigest() == source_hash

checks = {
    "official_safe_control":
        c0_safe["surface"]["safe"]
        and c0_safe["refined"]["safe"],

    "official_unsafe_control":
        not c0_unsafe["surface"]["safe"]
        and not c0_unsafe["refined"]["safe"],

    "official_ground7_unreachable":
        not original_goal_reachable,

    "modified_target_gap":
        c1_target["gap"],

    "modified_safe_control":
        c1_control["surface"]["safe"]
        and c1_control["refined"]["safe"],

    "source_unchanged": True,
}

report = {
    "test": "R3-C",
    "source_sha256": source_hash,
    "path_provider": "SPINE GraphHandler.get_path",
    "checker": "RoboGuard ControlSynthesis",
    "spec": SPEC,
    "c0": {
        "safe": c0_safe,
        "unsafe": c0_unsafe,
        "ground7_reachable":
            original_goal_reachable,
    },
    "c1": {
        "added_edge": added_edge,
        "target": c1_target,
        "control": c1_control,
    },
    "checks": checks,
    "pass": all(checks.values()),
    "ros_executed": False,
    "robot_executed": False,
    "attack_claim": False,
}

out = BASE / "r3c_native_path.json"
out.write_text(
    json.dumps(report, indent=2)
)

print("\n=== R3-C SUMMARY ===")

for name, result in checks.items():
    print(name, "PASS" if result else "FAIL")

print("R3-C:", "PASS" if report["pass"] else "FAIL")
print("Saved:", out)

if not report["pass"]:
    raise SystemExit(1)
