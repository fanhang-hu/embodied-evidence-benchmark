import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
import importlib.util
from pathlib import Path

PROJECT = Path("external/selp").resolve()
OUT = Path("results/E3/selp/e1_official_ltl_smoke.json")

sys.path.insert(0, str(PROJECT / "src"))

print("=== SELP E1: Official LTL Smoke Test ===")
print("Project:", PROJECT)
print("Python:", sys.version.split()[0])

# Spot is the official SELP semantic LTL engine.
if importlib.util.find_spec("spot") is None:
    print("SPOT: NOT INSTALLED")
    print("SELP-E1 BLOCKED: missing Spot")
    sys.exit(2)

import spot

if not all(
    hasattr(spot, attr)
    for attr in ("formula", "are_equivalent")
):
    print("SPOT: incompatible Python module")
    print("SELP-E1 BLOCKED: incompatible Spot")
    sys.exit(2)

print("SPOT: AVAILABLE")

from selp.ltl import is_valid_formula, are_equivalent
from selp.equivalence_voting import majority_vote

safe_a = "G(!unsafe)"
safe_b = "!F(unsafe)"
unsafe_a = "F(unsafe)"
invalid = "G("

print("\n=== Syntax Validation ===")

assert is_valid_formula(safe_a)
assert is_valid_formula(safe_b)
assert is_valid_formula(unsafe_a)
assert not is_valid_formula(invalid)

print("Valid formulas: 3/3")
print("Invalid formula rejected: 1/1")

print("\n=== Semantic Equivalence ===")

assert are_equivalent(safe_a, safe_b)
assert not are_equivalent(safe_a, unsafe_a)

print("Equivalent safe formulas: PASS")
print("Non-equivalent unsafe formula: PASS")

print("\n=== Official Majority Voting ===")

candidates = [
    safe_a,
    safe_b,
    unsafe_a,
    invalid,
]

result = majority_vote(
    candidates,
    ground_truth_formula=safe_a,
)

print(json.dumps(result, indent=2))

assert result["majority_vote_acc"] is True
assert result["majority_formula"] != "SyntaxError"
assert are_equivalent(result["majority_formula"], safe_a)
assert len(result["syntax_errors"]) == 1

report = {
    "experiment": "SELP-E1",
    "implementation": "official SELP source",
    "component": "LTL semantic equivalence voting",
    "status": "PASS",
    "official_model_weights_loaded": False,
    "actual_llm_inference": False,
    "safe_equivalence": True,
    "unsafe_non_equivalence": True,
    "voting": result,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))

print("\nSELP-E1 PASS")
print("Saved:", OUT)
