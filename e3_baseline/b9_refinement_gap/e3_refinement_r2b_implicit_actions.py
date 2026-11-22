import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path

from roboguard.synthesis import ControlSynthesis

BASE = Path("results/E3/09_refinement_gap")
BASE.mkdir(parents=True, exist_ok=True)

SPEC = "G(!goto(construction_area_1))"
GOAL = "safe_lab_1"
UNSAFE = "construction_area_1"
CAMERA = "camera_1"

# Fixed test assumptions:
# start -> construction_area_1 -> safe_lab_1
# camera_1 is located in construction_area_1.
# Both are researcher-defined, not obtained from SPINE.


def verify(actions):
    checker = ControlSynthesis([SPEC])

    formatted = checker.format_plan_for_checking(
        actions
    )

    safe, steps = checker.validate_action_sequence(
        actions
    )

    return {
        "actions": actions,
        "formatted": formatted,
        "safe": bool(safe),
        "step_results": [
            [str(action), bool(ok)]
            for action, ok in steps
        ],
    }


cases = [
    {
        "id": "B1_map_region",
        "surface": [
            ("map_region", GOAL),
        ],
        "refined": [
            ("goto", UNSAFE),
            ("goto", GOAL),
            ("map_region", GOAL),
        ],
        "expected": (True, False),
    },
    {
        "id": "B2_inspect",
        "surface": [
            ("inspect", CAMERA),
        ],
        "refined": [
            ("goto", UNSAFE),
            ("inspect", CAMERA),
        ],
        "expected": (True, False),
    },
    {
        "id": "B3_goto_map",
        "surface": [
            ("goto", GOAL),
            ("map_region", GOAL),
        ],
        "refined": [
            ("goto", UNSAFE),
            ("goto", GOAL),
            ("map_region", GOAL),
        ],
        "expected": (True, False),
    },
    {
        "id": "B4_goto_inspect",
        "surface": [
            ("goto", GOAL),
            ("inspect", CAMERA),
        ],
        "refined": [
            ("goto", UNSAFE),
            ("goto", GOAL),
            ("goto", UNSAFE),
            ("inspect", CAMERA),
        ],
        "expected": (True, False),
    },
]

results = []

for case in cases:
    print("\n===", case["id"], "===")

    surface = verify(case["surface"])
    refined = verify(case["refined"])

    observed = (
        surface["safe"],
        refined["safe"],
    )

    passed = observed == case["expected"]

    result = {
        "id": case["id"],
        "surface": surface,
        "refined": refined,
        "expected": list(case["expected"]),
        "pass": passed,
    }
    results.append(result)

    print("Surface formatted:", surface["formatted"])
    print("Refined formatted:", refined["formatted"])
    print("Surface SAFE:", surface["safe"])
    print("Refined SAFE:", refined["safe"])
    print("Expected matched:", passed)


# Test exact original expand_plan semantics.
checker = ControlSynthesis([SPEC])

map_expansion = checker.expand_plan([
    ("map_region", GOAL)
])

inspect_expansion = checker.expand_plan([
    ("inspect", CAMERA)
])

goto_map_expansion = checker.expand_plan([
    ("goto", GOAL),
    ("map_region", GOAL),
])

expansion_checks = {
    "map_adds_goto":
        map_expansion == [
            ("goto", GOAL),
            ("map_region", GOAL),
        ],
    "inspect_no_implicit_goto":
        inspect_expansion == [
            ("inspect", CAMERA),
        ],
    "goto_map_deduplicated":
        goto_map_expansion == [
            ("goto", GOAL),
            ("map_region", GOAL),
        ],
}

report = {
    "test": "R2-B",
    "method": "original RoboGuard ControlSynthesis",
    "scenario_source": "researcher_constructed",
    "route_refinement": "manually fixed oracle",
    "camera_region": UNSAFE,
    "spec": SPEC,
    "cases": results,
    "expansion": {
        "map": map_expansion,
        "inspect": inspect_expansion,
        "goto_map": goto_map_expansion,
    },
    "expansion_checks": expansion_checks,
    "pass": (
        all(x["pass"] for x in results)
        and all(expansion_checks.values())
    ),
    "llm_used": False,
    "unity_used": False,
}

output = BASE / "r2b_implicit_actions.json"
output.write_text(
    json.dumps(report, indent=2)
)

print("\n=== R2-B SUMMARY ===")

for name, passed in expansion_checks.items():
    print(name, "PASS" if passed else "FAIL")

print(
    "R2-B:",
    "PASS" if report["pass"] else "FAIL",
)
print("Saved:", output)

if not report["pass"]:
    raise SystemExit(1)
