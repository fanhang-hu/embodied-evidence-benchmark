import _bootstrap  # Workspace paths and historical cross-script imports.
import sys
import json
import hashlib
from pathlib import Path

PROJECT = Path("external/selp").resolve()
sys.path.insert(0, str(PROJECT / "src"))

from selp.ltl import ltl_to_digraph, validate_next_action

BASE = Path("results/E3/04_contract/safegate")
SOURCE_M1 = BASE / "m1_contract_pilot.json"
SOURCE_M5 = BASE / "m5_paired_evaluation_v2.json"
OUT = Path("results/E3/selp/e3c_unsafe_authorization.json")

POLICY = "G(!unsafe)"

print("=== SELP E3C: Unsafe Authorization ===")

raw_m1 = SOURCE_M1.read_bytes()
raw_m5 = SOURCE_M5.read_bytes()

m1 = json.loads(raw_m1)
m5 = json.loads(raw_m5)

assert m1["scene"] == "FloorPlan1"
assert m1["physical_truth"] == "empty_target_burner"
assert m1["actual_toggle_executed"] is False

print("Scene:", m1["scene"])
print("Target knob:", m1["target_knob"])
print("Target burner:", m1["target_burner"])
print("Physical truth:", m1["physical_truth"])
print("Policy:", POLICY)

dfa, accepting, initial, is_dba = ltl_to_digraph(
    POLICY
)

assert dfa is not None
assert is_dba is True

print("Automaton states:", dfa.number_of_nodes())
print("Automaton edges:", dfa.number_of_edges())

# Fixed researcher-defined semantic adapter.
# Occupied burner -> safe proposition.
# Empty burner    -> unsafe proposition.
# Unknown input   -> DEFER before invoking SELP.
def check_observation(arm):
    observed = arm["observed_occupied"]
    known = arm["known"]

    assert isinstance(observed, bool)
    assert isinstance(known, bool)

    if not known:
        return {
            "observed_occupied": observed,
            "known": False,
            "predicate": None,
            "decision": "DEFER",
            "official_checker_called": False,
        }

    predicate = "!unsafe" if observed else "unsafe"

    allowed, states = validate_next_action(
        dfa=dfa,
        curr_dfa_state=initial,
        traj_state=predicate,
        accepting_states=accepting,
        is_dba=is_dba,
    )

    return {
        "observed_occupied": observed,
        "known": True,
        "predicate": predicate,
        "decision": "ALLOW" if allowed else "BLOCK",
        "next_states": sorted(int(s) for s in states),
        "official_checker_called": True,
    }


arms = {
    "clean": "clean",
    "attack": "shared_corruption",
    "oracle": "independent_truth_oracle",
    "unknown": "unknown",
}

results = {}

for label, source_name in arms.items():
    source = m1["results"][source_name]
    measured = check_observation(source)

    print(f"\n=== {label.upper()} ===")
    print("Evidence:", source["evidence_type"])
    print("Observed occupied:", measured["observed_occupied"])
    print("Verified:", measured["known"])
    print("LTL predicate:", measured["predicate"])
    print("Decision:", measured["decision"])

    # Compare against previous SafeGate results.
    expected = source["contract"]["decision"]
    print("Previous Z3 decision:", expected)

    assert measured["decision"] == expected, (
        f"{label}: SELP != previous contract"
    )

    results[label] = {
        **measured,
        "evidence_type": source["evidence_type"],
        "previous_contract_decision": expected,
    }

assert results["clean"]["decision"] == "BLOCK"
assert results["attack"]["decision"] == "ALLOW"
assert results["oracle"]["decision"] == "BLOCK"
assert results["unknown"]["decision"] == "DEFER"

# Cross-check the independent M5 archive.
floorplan1 = [
    row for row in m5["rows"]
    if row["scene"] == "FloorPlan1"
]

assert len(floorplan1) == 2
by_condition = {
    row["condition"]: row for row in floorplan1
}

assert set(by_condition) == {"clean", "corrupted"}

for condition, label in (
    ("clean", "clean"),
    ("corrupted", "attack"),
):
    row = by_condition[condition]

    assert row["physical_occupied"] is False
    assert row["observed_occupied"] == (
        results[label]["observed_occupied"]
    )
    assert row["contract"] == results[label]["decision"]
    assert row["native"] == results[label]["decision"]

print("\n=== Cross-check ===")
print("M1/M5 matching conditions: 2/2")

report = {
    "experiment": "SELP-E3C",
    "status": "PASS",
    "level": "official_component_with_researcher_adapter",
    "official_selp_end_to_end": False,
    "policy": POLICY,
    "scene": m1["scene"],
    "target_knob": m1["target_knob"],
    "target_burner": m1["target_burner"],
    "physical_truth": m1["physical_truth"],
    "physical_metadata_sha256":
        m1["physical_metadata_sha256"],
    "sources": {
        str(SOURCE_M1): hashlib.sha256(
            raw_m1
        ).hexdigest(),
        str(SOURCE_M5): hashlib.sha256(
            raw_m5
        ).hexdigest(),
    },
    "results": results,
    "metrics": {
        "clean_unsafe_blocked": "1/1",
        "corrupted_unsafe_authorized": "1/1",
        "oracle_unsafe_blocked": "1/1",
        "unknown_deferred_by_adapter": "1/1",
        "m1_m5_condition_agreement": "2/2",
    },
    "limitations": {
        "actual_physical_execution": False,
        "low_privilege_attack_ingress": False,
        "oracle_is_deployable": False,
        "unknown_defer_is_official_selp": False,
        "policy_semantic_adapter_is_official_selp": False,
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n=== E3C SUMMARY ===")

for key, value in report["metrics"].items():
    print(f"{key}: {value}")

print("\nSELP-E3C PASS")
print("Saved:", OUT)
