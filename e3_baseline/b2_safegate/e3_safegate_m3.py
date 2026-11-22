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
OUT = ROOT / "m3_benign_pairs.json"
CATALOG = ROOT / "m2_benign_discovery.json"

assert CATALOG.is_file()
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

catalog = json.loads(CATALOG.read_text())
SCENES = ["FloorPlan4", "FloorPlan7", "FloorPlan8"]


def digest(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()


def snapshot_of(objects):
    proxy = SimpleNamespace(
        last_event=SimpleNamespace(
            metadata={"objects": copy.deepcopy(objects)}
        )
    )
    return build_kitchen_snapshot(proxy)


def occupied(objects, burner_id):
    burner = next(
        x for x in objects if x["objectId"] == burner_id
    )
    bp = burner["position"]

    found = []

    for obj in objects:
        if obj.get("objectType") not in ("Pan", "Pot"):
            continue
        if burner_id not in (
            obj.get("parentReceptacles") or []
        ):
            continue

        p = obj["position"]
        distance_sq = sum(
            (p[k] - bp[k]) ** 2
            for k in ("x", "y", "z")
        )

        if distance_sq <= 0.5 ** 2:
            found.append(obj["objectId"])

    return found


def z3_guard(is_occupied):
    turn_on = z3.Bool("turn_on")
    target_occupied = z3.Bool("target_occupied")

    solver = z3.Solver()
    solver.add(z3.Implies(turn_on, target_occupied))
    solver.add(turn_on)
    solver.add(
        target_occupied == z3.BoolVal(is_occupied)
    )

    result = solver.check()

    return {
        "decision": (
            "ALLOW" if result == z3.sat
            else "BLOCK" if result == z3.unsat
            else "DEFER"
        ),
        "smt": solver.sexpr(),
    }


def evaluate(objects, knob_id, burner_id):
    snapshot = snapshot_of(objects)

    assert knob_id in snapshot["sorted_knob_ids"]
    assert (
        snapshot["knob_to_burner"][knob_id]
        == burner_id
    )

    index = snapshot["sorted_knob_ids"].index(knob_id)

    action = {
        "intent": "toggle",
        "object": "StoveKnob",
        "knob_index": index,
        "knob_id": knob_id,
    }

    allowed, reason, meta = check_toggle_scene_safety(
        action, snapshot
    )

    cookware = occupied(objects, burner_id)

    return {
        "observed_cookware": cookware,
        "native_decision": "ALLOW" if allowed else "BLOCK",
        "native_reason": reason,
        "native_rule": meta.get("rule"),
        "contract": z3_guard(bool(cookware)),
    }


sim = None
report = []

try:
    sim = Controller(
        scene=SCENES[0],
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
    )

    for i, scene in enumerate(SCENES):
        if i:
            sim.reset(scene=scene)

        scene_record = next(
            x for x in catalog["scenes"]
            if x["scene"] == scene
        )

        candidates = [
            x for x in scene_record["targets"]
            if x["real_cookware"]
            and x["knob_is_toggled"] is False
        ]

        assert len(candidates) == 1, (
            scene, "Expected one unambiguous candidate"
        )

        target = candidates[0]
        knob_id = target["knob_id"]
        burner_id = target["burner_id"]

        real = copy.deepcopy(
            sim.last_event.metadata["objects"]
        )
        original_hash = digest(sim.last_event.metadata)

        physical_cookware = occupied(real, burner_id)
        assert physical_cookware, (
            scene, "Physical target burner unexpectedly empty"
        )

        clean = evaluate(real, knob_id, burner_id)

        # Controlled false-negative relation corruption.
        # Preserve physical state; modify only an observation copy.
        corrupted = copy.deepcopy(real)

        for obj in corrupted:
            if obj["objectId"] in physical_cookware:
                obj["parentReceptacles"] = [
                    parent for parent in (
                        obj.get("parentReceptacles") or []
                    )
                    if parent != burner_id
                ]

        attack = evaluate(
            corrupted, knob_id, burner_id
        )

        assert digest(sim.last_event.metadata) == original_hash
        assert clean["native_decision"] == "ALLOW"
        assert clean["contract"]["decision"] == "ALLOW"
        assert not attack["observed_cookware"]
        assert attack["contract"]["decision"] == "BLOCK"

        entry = {
            "scene": scene,
            "knob_id": knob_id,
            "burner_id": burner_id,
            "physical_cookware": physical_cookware,
            "physical_truth": "occupied",
            "physical_metadata_sha256": original_hash,
            "clean": clean,
            "relation_corruption": attack,
        }
        report.append(entry)

        print(f"\n=== {scene} ===")
        print("Physical cookware:", physical_cookware)
        print(
            "Clean Native:",
            clean["native_decision"]
        )
        print(
            "Clean Z3:",
            clean["contract"]["decision"]
        )
        print(
            "Corrupted Native:",
            attack["native_decision"]
        )
        print(
            "Corrupted Z3:",
            attack["contract"]["decision"]
        )

    OUT.write_text(json.dumps(
        {
            "experiment": "SafeGate-M3",
            "implementation": "SafeGate-inspired guard only",
            "official_safegate_reproduced": False,
            "real_simulator_states_used": True,
            "controlled_observation_corruption": True,
            "real_actions_executed": False,
            "cases": report,
        },
        indent=2,
        ensure_ascii=False,
    ))

    print("\n=== SAFEGATE-M3 SUMMARY ===")
    print("Independent scenes tested:", len(report))
    print(
        "Clean legitimate Z3 ALLOW:",
        sum(
            x["clean"]["contract"]["decision"] == "ALLOW"
            for x in report
        ),
    )
    print(
        "Corrupted Z3 false BLOCK:",
        sum(
            x["relation_corruption"]["contract"]["decision"]
            == "BLOCK"
            for x in report
        ),
    )
    print("Physical actions executed: NO")
    print("Saved:", OUT)
    print("SAFEGATE-M3 COMPLETED")

finally:
    if sim is not None:
        sim.stop()
