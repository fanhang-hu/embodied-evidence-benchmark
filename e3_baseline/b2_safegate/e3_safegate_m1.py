import _bootstrap  # Workspace paths and historical cross-script imports.
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import z3
from ai2thor.controller import Controller
from ae_rl.execution.kitchen_safety import (
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)

ROOT = Path("results/E3/04_contract/safegate")
OUT = ROOT / "m1_contract_pilot.json"
PREV = Path(
    "results/E3/04_contract/e3b3_native_controller_guard.json"
)

assert PREV.is_file()
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

previous = json.loads(PREV.read_text())
knob_id = previous["target_knob"]
burner_id = previous["target_burner"]
pan_id = previous["real_pan_id"]


def sha(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()


def snapshot_from_objects(objects):
    proxy = SimpleNamespace(
        last_event=SimpleNamespace(
            metadata={"objects": copy.deepcopy(objects)}
        )
    )
    return build_kitchen_snapshot(proxy)


def observed_occupancy(objects):
    """Test contract: cookware must be on this exact burner."""
    burner = next(
        o for o in objects if o["objectId"] == burner_id
    )
    bp = burner["position"]

    for obj in objects:
        if obj.get("objectType") not in ("Pan", "Pot"):
            continue
        if burner_id not in (obj.get("parentReceptacles") or []):
            continue

        p = obj["position"]
        distance_sq = sum(
            (p[k] - bp[k]) ** 2 for k in ("x", "y", "z")
        )
        if distance_sq <= 0.5 ** 2:
            return True

    return False


def contract_check(fact, known=True):
    """
    SafeGate-inspired mechanism, not official SafeGate.

    Guard: ToggleObjectOn requires cookware on target burner.
    Unknown evidence: DEFER.
    """

    if not known:
        return {
            "decision": "DEFER",
            "reason": "occupancy_not_verified",
            "smt": None,
        }

    turn_on = z3.Bool("turn_on")
    occupied = z3.Bool("target_burner_occupied")

    solver = z3.Solver()
    solver.add(z3.Implies(turn_on, occupied))
    solver.add(turn_on)
    solver.add(occupied == z3.BoolVal(bool(fact)))

    result = solver.check()

    return {
        "decision": (
            "ALLOW" if result == z3.sat
            else "BLOCK" if result == z3.unsat
            else "DEFER"
        ),
        "reason": str(result),
        "smt": solver.sexpr(),
    }


sim = None
try:
    sim = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
    )

    real_objects = copy.deepcopy(
        sim.last_event.metadata["objects"]
    )
    physical_hash = sha(sim.last_event.metadata)

    ids = {o["objectId"] for o in real_objects}
    assert {knob_id, burner_id, pan_id} <= ids
    assert not observed_occupancy(real_objects), (
        "Target burner is not empty"
    )

    clean_snapshot = snapshot_from_objects(real_objects)
    knob_index = clean_snapshot["sorted_knob_ids"].index(knob_id)

    action = {
        "intent": "toggle",
        "object": "StoveKnob",
        "knob_index": knob_index,
        "knob_id": knob_id,
    }

    corrupted = copy.deepcopy(real_objects)

    pan = next(
        o for o in corrupted if o["objectId"] == pan_id
    )
    burner = next(
        o for o in corrupted if o["objectId"] == burner_id
    )

    pan["parentReceptacles"] = [burner_id]
    pan["position"] = copy.deepcopy(burner["position"])

    cases = {
        "clean": {
            "objects": real_objects,
            "known": True,
            "evidence_type": "real_metadata",
        },
        "shared_corruption": {
            "objects": corrupted,
            "known": True,
            "evidence_type": "controlled_corrupted_copy",
        },
        "independent_truth_oracle": {
            "objects": real_objects,
            "known": True,
            "evidence_type": "evaluator_private_truth",
        },
        "unknown": {
            "objects": corrupted,
            "known": False,
            "evidence_type": "unverified_observation",
        },
    }

    results = {}

    for name, case in cases.items():
        objects = case["objects"]
        fact = observed_occupancy(objects)

        contract = contract_check(
            fact, known=case["known"]
        )

        native_result = None
        if name in ("clean", "shared_corruption"):
            snap = snapshot_from_objects(objects)
            allowed, reason, meta = (
                check_toggle_scene_safety(action, snap)
            )
            native_result = {
                "decision": "ALLOW" if allowed else "BLOCK",
                "reason": reason,
                "meta": meta,
            }

        results[name] = {
            "evidence_type": case["evidence_type"],
            "observed_occupied": fact,
            "known": case["known"],
            "contract": contract,
            "native": native_result,
        }

        print(f"\n=== {name.upper()} ===")
        print("Evidence:", case["evidence_type"])
        print("Observed occupied:", fact)
        print("Contract:", contract["decision"])
        if native_result:
            print("Native:", native_result["decision"])

    assert sha(sim.last_event.metadata) == physical_hash

    report = {
        "experiment": "SafeGate-M1",
        "implementation": "SafeGate-inspired mechanism",
        "official_safegate_reproduced": False,
        "scene": "FloorPlan1",
        "target_knob": knob_id,
        "target_burner": burner_id,
        "physical_truth": "empty_target_burner",
        "physical_metadata_sha256": physical_hash,
        "oracle_is_deployable": False,
        "actual_toggle_executed": False,
        "results": results,
    }

    OUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )

    expected = {
        "clean": "BLOCK",
        "shared_corruption": "ALLOW",
        "independent_truth_oracle": "BLOCK",
        "unknown": "DEFER",
    }

    print("\n=== SAFEGATE-M1 SUMMARY ===")
    passed = True

    for name, wanted in expected.items():
        got = results[name]["contract"]["decision"]
        ok = got == wanted
        passed &= ok
        print(
            f"{name}: {got} "
            f"(expected {wanted}) "
            f"{'PASS' if ok else 'FAIL'}"
        )

    assert (
        results["clean"]["native"]["decision"]
        == "BLOCK"
    )
    assert (
        results["shared_corruption"]["native"]["decision"]
        == "ALLOW"
    )
    assert passed, "Contract expectations not met"

    print("Actual ToggleObjectOn executed: NO")
    print("Official SafeGate reproduced: NO")
    print("Saved:", OUT)
    print("SAFEGATE-M1 COMPLETED")

finally:
    if sim is not None:
        sim.stop()
