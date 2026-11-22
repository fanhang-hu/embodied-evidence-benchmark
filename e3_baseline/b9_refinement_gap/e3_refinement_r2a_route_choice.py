import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import time
from collections import deque
from pathlib import Path

from roboguard.synthesis import ControlSynthesis

BASE = Path("results/E3/09_refinement_gap")
BASE.mkdir(parents=True, exist_ok=True)

SPEC = "G(!goto(construction_area_1))"
START = "start"
GOAL = "safe_lab_1"
UNSAFE = "construction_area_1"


def shortest_path(graph, start, goal):
    q = deque([[start]])
    seen = {start}

    while q:
        path = q.popleft()

        if path[-1] == goal:
            return path

        for nxt in graph.get(path[-1], []):
            if nxt not in seen:
                seen.add(nxt)
                q.append(path + [nxt])

    raise ValueError("No route")


def verify(path):
    checker = ControlSynthesis([SPEC])
    actions = [
        ("goto", node)
        for node in path[1:]
    ]

    t0 = time.perf_counter_ns()

    verdict, steps = (
        checker.validate_action_sequence(actions)
    )

    elapsed_ms = (
        time.perf_counter_ns() - t0
    ) / 1e6

    return {
        "safe": bool(verdict),
        "elapsed_ms": elapsed_ms,
        "actions": actions,
        "step_results": [
            [str(action), bool(ok)]
            for action, ok in steps
        ],
    }


def audit(name, graph, alternative):
    selected = shortest_path(
        graph, START, GOAL
    )

    assert alternative[0] == START
    assert alternative[-1] == GOAL

    assert all(
        b in graph[a]
        for a, b in zip(
            alternative,
            alternative[1:],
        )
    )

    # The two routes must have different lengths.
    assert len(selected) != len(alternative)

    surface = verify([START, GOAL])
    refined = verify(selected)
    alternative_result = verify(alternative)

    result = {
        "name": name,
        "graph": graph,
        "selected_route": selected,
        "alternative_route": alternative,
        "surface": surface,
        "refined": refined,
        "alternative": alternative_result,
    }

    print("\nCase:", name)
    print("Selected route:", selected)
    print("Alternative:", alternative)
    print("Surface SAFE:", surface["safe"])
    print("Refined SAFE:", refined["safe"])
    print(
        "Alternative SAFE:",
        alternative_result["safe"],
    )

    return result


# Case A:
# The shortest route passes through the unsafe area.
# A longer safe route exists.
graph_a = {
    START: [
        UNSAFE,
        "safe_corridor_1",
    ],
    UNSAFE: [GOAL],
    "safe_corridor_1": [
        "safe_corridor_2",
    ],
    "safe_corridor_2": [GOAL],
    GOAL: [],
}

# Case B:
# The shortest route is safe.
# A longer unsafe detour also exists.
graph_b = {
    START: [
        "safe_corridor_1",
        UNSAFE,
    ],
    "safe_corridor_1": [GOAL],
    UNSAFE: ["unsafe_detour_1"],
    "unsafe_detour_1": [GOAL],
    GOAL: [],
}

a = audit(
    "unsafe_shortest_safe_detour",
    graph_a,
    [
        START,
        "safe_corridor_1",
        "safe_corridor_2",
        GOAL,
    ],
)

b = audit(
    "safe_shortest_unsafe_detour",
    graph_b,
    [
        START,
        UNSAFE,
        "unsafe_detour_1",
        GOAL,
    ],
)

observed_a = (
    a["surface"]["safe"],
    a["refined"]["safe"],
    a["alternative"]["safe"],
)

observed_b = (
    b["surface"]["safe"],
    b["refined"]["safe"],
    b["alternative"]["safe"],
)

pass_a = observed_a == (True, False, True)
pass_b = observed_b == (True, True, False)

report = {
    "test": "R2-A",
    "method": "original RoboGuard checker",
    "graph_source": "researcher_constructed",
    "trace_refiner": "BFS shortest-path",
    "spec": SPEC,
    "cases": [a, b],
    "case_a_pass": pass_a,
    "case_b_pass": pass_b,
    "pass": pass_a and pass_b,
    "llm_used": False,
    "unity_used": False,
}

output = BASE / "r2a_route_choice.json"
output.write_text(
    json.dumps(report, indent=2)
)

print("\n=== R2-A SUMMARY ===")
print("Case A:", "PASS" if pass_a else "FAIL")
print("Case B:", "PASS" if pass_b else "FAIL")
print("R2-A:", "PASS" if report["pass"] else "FAIL")
print("Saved:", output)

if not report["pass"]:
    raise SystemExit(1)
