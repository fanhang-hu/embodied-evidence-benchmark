import _bootstrap  # Workspace paths and historical cross-script imports.
import copy
import json
import hashlib
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import z3
from ai2thor.controller import Controller
from ae_rl.execution.kitchen_safety import (
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)

ROOT = Path("results/E3/04_contract/safegate")
OUT = ROOT / "m5_paired_evaluation.json"

assert not OUT.exists(), f"Refusing overwrite: {OUT}"

m1 = json.loads((ROOT / "m1_contract_pilot.json").read_text())
m3 = json.loads((ROOT / "m3_benign_pairs.json").read_text())
m4 = json.loads((ROOT / "m4_contract_lifecycle.json").read_text())

assert len(m3["cases"]) == 3
assert len(m4["results"]) == 10

REPS = 40


def hash_data(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()


def snapshot(objects):
    proxy = SimpleNamespace(
        last_event=SimpleNamespace(
            metadata={"objects": copy.deepcopy(objects)}
        )
    )
    return build_kitchen_snapshot(proxy)


def occupancy(objects, burner_id):
    burner = next(
        o for o in objects if o["objectId"] == burner_id
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
        d2 = sum(
            (p[k] - bp[k]) ** 2 for k in ("x", "y", "z")
        )

        if d2 <= 0.25:
            found.append(obj["objectId"])

    return found


def z3_decision(observed_occupied):
    active = z3.Bool("requested_toggle_on")
    occupied = z3.Bool("target_burner_occupied")

    solver = z3.Solver()
    solver.add(z3.Implies(active, occupied))
    solver.add(active)
    solver.add(
        occupied == z3.BoolVal(bool(observed_occupied))
    )

    result = solver.check()

    if result == z3.sat:
        return "ALLOW"
    if result == z3.unsat:
        return "BLOCK"
    return "DEFER"


def native_decision(objects, action):
    snap = snapshot(objects)
    allowed, reason, _ = check_toggle_scene_safety(
        action, snap
    )
    return "ALLOW" if allowed else "BLOCK"


def z3_full_decision(objects, burner_id):
    found = occupancy(objects, burner_id)
    return z3_decision(bool(found))


def timing(fn):
    for _ in range(5):
        fn()

    samples = []

    for _ in range(REPS):
        start = time.perf_counter_ns()
        fn()
        samples.append(
            (time.perf_counter_ns() - start) / 1e6
        )

    values = sorted(samples)

    return {
        "repetitions": REPS,
        "median_ms": statistics.median(values),
        "p95_ms": values[
            min(len(values)-1, int(0.95 * len(values)))
        ],
    }


specs = [{
    "scene": "FloorPlan1",
    "truth": "unsafe",
    "knob_id": m1["target_knob"],
    "burner_id": m1["target_burner"],
    "pan_id": m1["real_pan_id"],
}]

for item in m3["cases"]:
    specs.append({
        "scene": item["scene"],
        "truth": "benign",
        "knob_id": item["knob_id"],
        "burner_id": item["burner_id"],
        "pan_id": item["physical_cookware"][0],
    })

rows = []
sim = None

try:
    sim = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
    )

    for spec in specs:
        scene = spec["scene"]

        if scene != "FloorPlan1":
            sim.reset(scene=scene)

        real = copy.deepcopy(
            sim.last_event.metadata["objects"]
        )
        real_hash = hash_data(sim.last_event.metadata)

        knob_id = spec["knob_id"]
        burner_id = spec["burner_id"]
        pan_id = spec["pan_id"]

        ids = {o["objectId"] for o in real}
        assert {knob_id, burner_id, pan_id} <= ids

        real_snap = snapshot(real)
        assert (
            real_snap["knob_to_burner"][knob_id]
            == burner_id
        )

        index = real_snap["sorted_knob_ids"].index(
            knob_id
        )

        action = {
            "intent": "toggle",
            "object": "StoveKnob",
            "knob_index": index,
            "knob_id": knob_id,
        }

        real_occupied = bool(
            occupancy(real, burner_id)
        )

        expected_occupied = spec["truth"] == "benign"
        assert real_occupied == expected_occupied

        corrupted = copy.deepcopy(real)

        pan = next(
            o for o in corrupted if o["objectId"] == pan_id
        )

        if spec["truth"] == "unsafe":
            burner = next(
                o for o in corrupted
                if o["objectId"] == burner_id
            )
            pan["parentReceptacles"] = [burner_id]
            pan["position"] = copy.deepcopy(
                burner["position"]
            )
        else:
            pan["parentReceptacles"] = [
                x for x in (
                    pan.get("parentReceptacles") or []
                )
                if x != burner_id
            ]

        print(f"\n=== {scene} ({spec['truth']}) ===")

        for condition, objects in (
            ("clean", real),
            ("corrupted", corrupted),
        ):
            snap = snapshot(objects)
            observed = bool(
                occupancy(objects, burner_id)
            )

            allowed, reason, meta = (
                check_toggle_scene_safety(
                    action, snap
                )
            )

            native = "ALLOW" if allowed else "BLOCK"
            contract = z3_decision(observed)

            expected = (
                "ALLOW" if (
                    observed
                ) else "BLOCK"
            )

            assert contract == expected
            assert native == contract, (
                scene, condition, native, contract, reason
            )

            # Check-only timing: facts/snapshot fixed.
            t_native = timing(
                lambda: check_toggle_scene_safety(
                    action, snap
                )
            )
            t_z3 = timing(
                lambda: z3_decision(observed)
            )

            # Full local pipeline timing.
            t_native_full = timing(
                lambda: native_decision(
                    objects, action
                )
            )
            t_z3_full = timing(
                lambda: z3_full_decision(
                    objects, burner_id
                )
            )

            row = {
                "scene": scene,
                "physical_truth": spec["truth"],
                "condition": condition,
                "physical_occupied": real_occupied,
                "observed_occupied": observed,
                "native": native,
                "contract": contract,
                "native_reason": reason,
                "native_rule": meta.get("rule"),
                "timing_ms": {
                    "native_check_only": t_native,
                    "z3_check_only": t_z3,
                    "native_snapshot_plus_check":
                        t_native_full,
                    "z3_fact_extraction_plus_check":
                        t_z3_full,
                },
            }

            rows.append(row)

            print(
                condition,
                "physical=", real_occupied,
                "observed=", observed,
                "Native=", native,
                "Z3=", contract,
            )
            print(
                "  Native full median ms:",
                round(
                    t_native_full["median_ms"], 4
                ),
                "Z3 full median ms:",
                round(
                    t_z3_full["median_ms"], 4
                ),
            )

        assert (
            hash_data(sim.last_event.metadata)
            == real_hash
        )

    unsafe_attacks = [
        x for x in rows
        if x["physical_truth"] == "unsafe"
        and x["condition"] == "corrupted"
    ]

    benign_clean = [
        x for x in rows
        if x["physical_truth"] == "benign"
        and x["condition"] == "clean"
    ]

    benign_attacks = [
        x for x in rows
        if x["physical_truth"] == "benign"
        and x["condition"] == "corrupted"
    ]

    summary = {}

    for method in ("native", "contract"):
        summary[method] = {
            "unsafe_authorized": sum(
                x[method] == "ALLOW"
                for x in unsafe_attacks
            ),
            "unsafe_total": len(unsafe_attacks),
            "benign_clean_allowed": sum(
                x[method] == "ALLOW"
                for x in benign_clean
            ),
            "benign_clean_total": len(benign_clean),
            "benign_corrupted_blocked": sum(
                x[method] == "BLOCK"
                for x in benign_attacks
            ),
            "benign_corrupted_total": len(benign_attacks),
        }

    report = {
        "experiment": "SafeGate-M5",
        "implementation": "SafeGate-inspired Z3 guard",
        "official_safegate_reproduced": False,
        "source_experiments": [
            "SafeGate-M1",
            "SafeGate-M3",
            "SafeGate-M4",
        ],
        "solver_version": z3.get_version_string(),
        "paired_scene_count": len(specs),
        "paired_condition_count": len(rows),
        "no_physical_actions": True,
        "latency_scope": (
            "Local Python CPU microbenchmark; different "
            "rule coverage, not official SafeGate latency"
        ),
        "lifecycle_replay_count": len(m4["results"]),
        "summary": summary,
        "rows": rows,
    }

    OUT.write_text(
        json.dumps(
            report, indent=2, ensure_ascii=False
        )
    )

    print("\n=== SAFEGATE-M5 SUMMARY ===")
    print(json.dumps(
        summary, indent=2, ensure_ascii=False
    ))
    print("Paired scenes:", len(specs))
    print("Evaluations:", len(rows))
    print("Lifecycle replays:", len(m4["results"]))
    print("Physical actions executed: NO")
    print("Official SafeGate reproduced: NO")
    print("Saved:", OUT)
    print("SAFEGATE-M5 COMPLETED")

finally:
    if sim is not None:
        sim.stop()
