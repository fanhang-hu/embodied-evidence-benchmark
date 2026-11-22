import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from spine.mapping.graph_util import GraphHandler
from roboguard.synthesis import ControlSynthesis

BASE = Path("results/E3/09_refinement_gap")
BASE.mkdir(parents=True, exist_ok=True)

REPO = Path("external/SPINE")
SRC = REPO / "ros/spine_ros/scripts/spine_node.py"
DATA = Path("external/RoboGuard/data/perch_small.json")

START = "ground_1"
UNSAFE = "construction_area_1"
SPEC = "G(!goto(construction_area_1))"

assert SRC.exists(), f"Missing original ROS source: {SRC}"
assert DATA.exists()

src_bytes = SRC.read_bytes()
src_hash = hashlib.sha256(src_bytes).hexdigest()

data_bytes = DATA.read_bytes()
data_hash = hashlib.sha256(data_bytes).hexdigest()

# Extract original methods, avoiding unavailable ROS imports.
tree = ast.parse(src_bytes.decode("utf-8"))

def find_method(name):
    matches = []
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef):
            for node in cls.body:
                if (
                    isinstance(node, ast.FunctionDef)
                    and node.name == name
                ):
                    matches.append(node)

    assert len(matches) == 1, (name, len(matches))
    assert not matches[0].decorator_list
    return copy.deepcopy(matches[0])

methods = [
    find_method("graph_nav_to_region"),
    find_method("_update_location"),
]

ros_logs = []

namespace = {
    "rospy": SimpleNamespace(
        loginfo=lambda msg: ros_logs.append(str(msg))
    )
}

module = ast.fix_missing_locations(
    ast.Module(body=methods, type_ignores=[])
)

exec(
    compile(module, str(SRC), "exec"),
    namespace
)


class OfflineNav:
    # Original method bodies; ROS service is mocked.
    graph_nav_to_region = namespace["graph_nav_to_region"]
    _update_location = namespace["_update_location"]

    def __init__(self, handler):
        self.graph = handler
        self.current_location = START
        self.location_history = [START]
        self.service_calls = []
        self.feedback = []

        self.llm_prompt_former = SimpleNamespace(
            update=lambda **kw: self.feedback.append(kw)
        )

    def navigate_to_region_srv_proxy(self, node):
        # Fake ROS navigation service: always succeeds.
        self.service_calls.append(node)
        return SimpleNamespace(success=True)


def verify(actions):
    checker = ControlSynthesis([SPEC])
    verdict, steps = checker.validate_action_sequence(
        actions
    )
    return {
        "safe": bool(verdict),
        "steps": [
            [str(action), bool(ok)]
            for action, ok in steps
        ],
    }


def audit(name, handler, goal, expected):
    ros_logs.clear()

    planned_path = handler.get_path(START, goal)

    # Checker sees high-level plan only.
    surface = verify([("goto", goal)])

    # Run original SPINE graph navigation method.
    nav = OfflineNav(handler)
    nav_success = nav.graph_nav_to_region(goal)

    # Refined trace comes from navigation-service calls.
    refined_actions = [
        ("goto", node)
        for node in nav.service_calls
    ]
    refined = verify(refined_actions)

    observed = (
        surface["safe"],
        refined["safe"],
    )

    checks = {
        "verdict": observed == expected,
        "navigation_success": nav_success is True,
        "service_trace_matches_native_path":
            nav.service_calls == planned_path[1:],
        "location_history_matches_path":
            nav.location_history == planned_path,
        "final_location": nav.current_location == goal,
    }

    result = {
        "name": name,
        "goal": goal,
        "native_path": planned_path,
        "navigation_service_calls": nav.service_calls,
        "location_history": nav.location_history,
        "surface": surface,
        "refined": refined,
        "checks": checks,
        "pass": all(checks.values()),
        "ros_logs": list(ros_logs),
        "service_is_mock": True,
    }

    print("\n===", name, "===")
    print("Native path:", planned_path)
    print("Service calls:", nav.service_calls)
    print("Location history:", nav.location_history)
    print("Surface SAFE:", surface["safe"])
    print("Refined SAFE:", refined["safe"])
    print("Case:", "PASS" if result["pass"] else "FAIL")

    return result


print("=== C0: ORIGINAL OFFICIAL GRAPH ===")

original = GraphHandler(
    str(DATA),
    init_node=START,
)

c0_safe = audit(
    "C0_safe",
    original,
    "ground_20",
    (True, True),
)

# Separate GraphHandler to avoid state contamination.
original_unsafe = GraphHandler(
    str(DATA),
    init_node=START,
)

# Diagnostic replay: mocked navigation is exercised even
# when the high-level checker rejects the request.
c0_unsafe = audit(
    "C0_unsafe",
    original_unsafe,
    UNSAFE,
    (False, False),
)


print("\n=== C1: MODIFIED GRAPH COPY ===")

modified_data = json.loads(data_bytes)
modified_data["region_connections"].append(
    [UNSAFE, "ground_7"]
)

modified = GraphHandler("", init_node=START)

assert modified.reset(
    json.dumps(modified_data),
    current_location=START,
)

c1_gap = audit(
    "C1_modified_gap",
    modified,
    "ground_7",
    (True, False),
)

source_unchanged = (
    hashlib.sha256(SRC.read_bytes()).hexdigest()
    == src_hash
    and hashlib.sha256(DATA.read_bytes()).hexdigest()
    == data_hash
)

report = {
    "test": "R3-D",
    "source_sha256": src_hash,
    "data_sha256": data_hash,
    "original_methods": [
        "graph_nav_to_region",
        "_update_location",
    ],
    "ros_service_mocked": True,
    "ros_runtime_started": False,
    "robot_executed": False,
    "llm_used": False,
    "cases": [
        c0_safe,
        c0_unsafe,
        c1_gap,
    ],
    "source_unchanged": source_unchanged,
}

report["pass"] = (
    all(c["pass"] for c in report["cases"])
    and source_unchanged
)

output = BASE / "r3d_native_nav.json"
output.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== R3-D SUMMARY ===")
print("Source unchanged:", source_unchanged)
print("R3-D:", "PASS" if report["pass"] else "FAIL")
print("Saved:", output)

if not report["pass"]:
    raise SystemExit(1)
