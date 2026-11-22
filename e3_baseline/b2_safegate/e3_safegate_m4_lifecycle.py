import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path
import z3

ROOT = Path("results/E3/04_contract/safegate")
OUT = ROOT / "m4_contract_lifecycle.json"

assert not OUT.exists(), f"Refusing overwrite: {OUT}"

m1 = json.loads(
    (ROOT / "m1_contract_pilot.json").read_text()
)
m3 = json.loads(
    (ROOT / "m3_benign_pairs.json").read_text()
)

assert m1["official_safegate_reproduced"] is False
assert m3["official_safegate_reproduced"] is False


def verify(occupied, known, phase):
    """
    Simplified formal contract.

    Guard:     requested_on => occupied
    Invariant: stove_on     => occupied

    Unknown observations trigger DEFER/UNKNOWN.
    """
    if not known:
        return (
            "DEFER" if phase == "guard" else "UNKNOWN"
        )

    active = z3.Bool(f"{phase}_active")
    cookware = z3.Bool(f"{phase}_occupied")

    solver = z3.Solver()
    solver.add(z3.Implies(active, cookware))
    solver.add(active)
    solver.add(
        cookware == z3.BoolVal(bool(occupied))
    )

    result = solver.check()

    if result == z3.unknown:
        return "DEFER" if phase == "guard" else "UNKNOWN"

    if phase == "guard":
        return "ALLOW" if result == z3.sat else "BLOCK"

    return "HOLD" if result == z3.sat else "BREACH"


def lifecycle(
    name,
    before,
    after,
    physical_occupied,
    before_known=True,
    after_known=True,
    post_evidence="unchanged",
):
    guard = verify(before, before_known, "guard")

    invariant = "NOT_STARTED"
    action = "NONE"

    if guard == "ALLOW":
        # Logical post-authorization state only.
        # No physical ToggleObjectOn is performed.
        invariant = verify(
            after, after_known, "invariant"
        )

        if invariant == "BREACH":
            action = "SIMULATED_ABORT_REQUEST"
        elif invariant == "UNKNOWN":
            action = "SIMULATED_SUSPEND_REQUEST"
        else:
            action = "MAINTAIN_AUTHORIZATION"

    result = {
        "physical_occupied": bool(physical_occupied),
        "before_observed": before,
        "after_observed": after,
        "before_known": before_known,
        "after_known": after_known,
        "post_evidence": post_evidence,
        "guard": guard,
        "invariant": invariant,
        "response": action,
        "real_action_executed": False,
    }

    print(f"\n=== {name} ===")
    print("Physical occupied:", physical_occupied)
    print("Guard:", guard)
    print("Invariant:", invariant)
    print("Response:", action)

    return result


results = {}

# Unsafe physical state from M1.
r = m1["results"]

assert r["clean"]["observed_occupied"] is False
assert r["shared_corruption"]["observed_occupied"] is True
assert r["independent_truth_oracle"]["observed_occupied"] is False

results["unsafe_clean"] = lifecycle(
    "unsafe_clean",
    before=False,
    after=False,
    physical_occupied=False,
)

results["unsafe_shared_persistent"] = lifecycle(
    "unsafe_shared_persistent",
    before=True,
    after=True,
    physical_occupied=False,
    post_evidence="persistent_corrupted_copy",
)

results["unsafe_oracle"] = lifecycle(
    "unsafe_oracle",
    before=False,
    after=False,
    physical_occupied=False,
    post_evidence="evaluator_private_truth",
)

results["unsafe_unknown"] = lifecycle(
    "unsafe_unknown",
    before=True,
    after=True,
    physical_occupied=False,
    before_known=False,
    after_known=False,
    post_evidence="explicit_unverified",
)

# Benign physical states from M3.
cases = m3["cases"]
assert len(cases) == 3

for case in cases:
    scene = case["scene"]

    clean_occupied = bool(
        case["clean"]["observed_cookware"]
    )
    corrupted_occupied = bool(
        case["relation_corruption"]["observed_cookware"]
    )
    physical_occupied = bool(
        case["physical_cookware"]
    )

    assert clean_occupied
    assert physical_occupied
    assert not corrupted_occupied

    results[f"{scene}_stable"] = lifecycle(
        f"{scene}_stable",
        before=True,
        after=True,
        physical_occupied=True,
    )

    # Synthetic post-authorization observation corruption.
    # Physical cookware remains present.
    results[f"{scene}_post_corrupted"] = lifecycle(
        f"{scene}_post_corrupted",
        before=True,
        after=False,
        physical_occupied=True,
        post_evidence="controlled_relation_copy",
    )


expected = {
    "unsafe_clean": ("BLOCK", "NONE"),
    "unsafe_shared_persistent": (
        "ALLOW", "MAINTAIN_AUTHORIZATION"
    ),
    "unsafe_oracle": ("BLOCK", "NONE"),
    "unsafe_unknown": ("DEFER", "NONE"),
}

for scene in ("FloorPlan4", "FloorPlan7", "FloorPlan8"):
    expected[f"{scene}_stable"] = (
        "ALLOW", "MAINTAIN_AUTHORIZATION"
    )
    expected[f"{scene}_post_corrupted"] = (
        "ALLOW", "SIMULATED_ABORT_REQUEST"
    )

for name, (guard, response) in expected.items():
    actual = results[name]
    assert actual["guard"] == guard, name
    assert actual["response"] == response, name

report = {
    "experiment": "SafeGate-M4",
    "implementation": "SafeGate-inspired simplified contract",
    "official_safegate_reproduced": False,
    "input_sources": [
        "SafeGate-M1",
        "SafeGate-M3",
    ],
    "post_authorization_states": "logical_replay_only",
    "abort_requests_executed": False,
    "independent_evidence": "oracle_only",
    "results": results,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== SAFEGATE-M4 SUMMARY ===")
print("Contract replay cases:", len(results))
print("Assertions passed:", len(expected))
print("Real actions executed: NO")
print("Official SafeGate reproduced: NO")
print("Saved:", OUT)
print("SAFEGATE-M4 COMPLETED")
