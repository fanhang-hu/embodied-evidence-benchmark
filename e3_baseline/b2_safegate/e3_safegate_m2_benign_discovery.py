import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path

from ai2thor.controller import Controller
from ae_rl.execution.kitchen_safety import (
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)

OUT = Path(
    "results/E3/04_contract/safegate/"
    "m2_benign_discovery.json"
)

assert not OUT.exists(), f"Refusing overwrite: {OUT}"

report = []
sim = None

try:
    sim = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
    )

    for scene_num in range(1, 11):
        scene = f"FloorPlan{scene_num}"

        if scene_num > 1:
            sim.reset(scene=scene)

        objects = sim.last_event.metadata["objects"]
        by_id = {o["objectId"]: o for o in objects}

        snapshot = build_kitchen_snapshot(sim)

        print(f"\n=== {scene} ===")

        scene_result = {
            "scene": scene,
            "targets": [],
        }

        for knob_index, knob_id in enumerate(
            snapshot["sorted_knob_ids"]
        ):
            burner_id = snapshot[
                "knob_to_burner"
            ].get(knob_id)

            if not burner_id:
                continue

            knob = by_id.get(knob_id)
            burner = by_id.get(burner_id)

            if knob is None or burner is None:
                continue

            cookware = [
                o["objectId"]
                for o in objects
                if o.get("objectType") in ("Pan", "Pot")
                and burner_id in (
                    o.get("parentReceptacles") or []
                )
            ]

            action = {
                "intent": "toggle",
                "object": "StoveKnob",
                "knob_index": knob_index,
                "knob_id": knob_id,
            }

            allowed, reason, meta = (
                check_toggle_scene_safety(
                    action, snapshot
                )
            )

            result = {
                "knob_id": knob_id,
                "burner_id": burner_id,
                "knob_is_toggled": knob.get(
                    "isToggled"
                ),
                "real_cookware": cookware,
                "native_allowed": bool(allowed),
                "native_reason": reason,
                "native_rule": meta.get("rule"),
            }

            scene_result["targets"].append(result)

            if cookware:
                print("REAL COOKWARE CANDIDATE")
                print("  Knob:", knob_id)
                print("  Burner:", burner_id)
                print("  Cookware:", cookware)
                print("  Knob ON:", knob.get("isToggled"))
                print(
                    "  Native:",
                    "ALLOW" if allowed else "BLOCK"
                )
                print("  Reason:", reason)

        report.append(scene_result)

    candidates = [
        (scene["scene"], target)
        for scene in report
        for target in scene["targets"]
        if target["real_cookware"]
        and target["knob_is_toggled"] is False
    ]

    OUT.write_text(
        json.dumps(
            {
                "experiment": "SafeGate-M2",
                "purpose": "real_benign_scene_discovery",
                "unsafe_actions_executed": False,
                "scenes": report,
                "candidate_count": len(candidates),
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== SAFEGATE-M2 SUMMARY ===")
    print("Scanned scenes:", len(report))
    print("Real benign candidates:", len(candidates))

    for scene, target in candidates:
        print(
            scene,
            target["burner_id"],
            "native_allowed=",
            target["native_allowed"],
        )

    print("Unsafe actions executed: NO")
    print("Saved:", OUT)
    print("SAFEGATE-M2 DISCOVERY COMPLETE")

finally:
    if sim is not None:
        sim.stop()
