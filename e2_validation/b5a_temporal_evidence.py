"""E2-B5A: Real pan-on-target -> pan-removed state transition.

Produces synchronized images and native monitor decisions in one AI2-THOR
controller session, to test visual-evidence freshness in a later step.
No adversarial file write, no simulator-metadata injection, no stove activation.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.
import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image
from ai2thor.controller import Controller
from b2_benign_stove_setup import (
    obj_by_id, status, build_kitchen_snapshot, check_toggle_scene_safety,
)

ROOT = Path.cwd()
OUT = ROOT / "results/e2b5"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "real_state_transition.json"
assert not REPORT.exists(), f"Existing report: {REPORT}"

m5 = json.loads((ROOT / "results/m5_real_state_pair.json").read_text())
view = json.loads(
    (ROOT / "results/m6_vision/stove_view_manifest.json").read_text()
)["best"]["pose"]

pan_id = m5["real_cookware_id"]
burner_id = m5["burner_id"]
knob_id = m5["knob_id"]

ROI = (90, 100, 210, 180)
logs = []
c = None


def checked(label, **kwargs):
    event = c.step(**kwargs)
    ok, err = status(event)
    logs.append({"label": label, "success": ok, "error": err})
    print(f"{label}: success={ok}, error={err[:120]}", flush=True)
    assert ok, f"{label} failed: {err}"
    return event


def teleport(label, pose):
    p = pose["position"]
    return checked(
        label, action="TeleportFull",
        x=p["x"], y=p["y"], z=p["z"],
        rotation={"x": 0, "y": pose["heading"], "z": 0},
        horizon=pose["horizon"],
        standing=True,
    )


def capture(label, expected_parent, expected_native):
    observed_ns = time.monotonic_ns()
    objs = c.last_event.metadata["objects"]

    pan = obj_by_id(objs, pan_id)
    parents = pan.get("parentReceptacles") or []

    assert (burner_id in parents) == expected_parent
    assert obj_by_id(objs, knob_id)["isToggled"] is False

    snap = build_kitchen_snapshot(c)
    assert snap["knob_to_burner"][knob_id] == burner_id

    allowed, reason, info = check_toggle_scene_safety(
        {
            "intent": "toggle",
            "object": "StoveKnob",
            "knob_id": knob_id,
        },
        snap,
    )

    decision = "ALLOW" if allowed else "BLOCK"
    assert decision == expected_native, (decision, reason, info)

    if not expected_parent:
        assert info.get("rule") == "empty_burner_toggle"

    source = OUT / f"{label}.png"

    image = Image.fromarray(
        np.asarray(c.last_event.frame, dtype=np.uint8)
    )
    image.save(source, format="PNG")

    roi = OUT / f"{label}_roi.png"
    image.crop(ROI).resize(
        (600, 400),
        Image.Resampling.LANCZOS
    ).save(roi)

    return {
        "observation_monotonic_ns": observed_ns,
        "image_file": str(source.relative_to(ROOT)),
        "roi_file": str(roi.relative_to(ROOT)),
        "image_sha256": hashlib.sha256(
            source.read_bytes()
        ).hexdigest(),
        "roi_sha256": hashlib.sha256(
            roi.read_bytes()
        ).hexdigest(),
        "pan_on_target": burner_id in parents,
        "pan_parents": parents,
        "native_decision": decision,
        "native_rule": info.get("rule"),
        "knob_off": True,
    }


try:
    c = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True,
    )

    objects = deepcopy(c.last_event.metadata["objects"])

    original_parents = (
        obj_by_id(objects, pan_id).get("parentReceptacles") or []
    )
    countertop_ids = [
        x for x in original_parents
        if x.startswith("CounterTop|")
    ]

    assert countertop_ids, (
        f"Pan not initially on countertop: {original_parents}"
    )
    original_counter = countertop_ids[0]

    snap = build_kitchen_snapshot(c)

    assert snap["knob_to_burner"][knob_id] == burner_id
    assert not snap["burner_objects"].get(burner_id)
    assert not obj_by_id(objects, knob_id)["isToggled"]

    # T0: establish a genuinely safe state.
    checked(
        "pickup_initial_pan",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )
    assert obj_by_id(
        c.last_event.metadata["objects"], pan_id
    )["isPickedUp"]

    checked(
        "put_pan_on_target",
        action="PutObject",
        objectId=burner_id,
        forceAction=True,
        placeStationary=True,
    )

    assert burner_id in (
        obj_by_id(
            c.last_event.metadata["objects"], pan_id
        ).get("parentReceptacles") or []
    )

    teleport("view_pan_on_target", view)
    before = capture(
        "t0_pan_on_target", True, "ALLOW"
    )

    # T1: genuinely remove Pan without switching the stove on.
    checked(
        "pickup_pan_from_burner",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    assert obj_by_id(
        c.last_event.metadata["objects"], pan_id
    )["isPickedUp"]

    checked(
        "restore_pan_to_countertop",
        action="PutObject",
        objectId=original_counter,
        forceAction=True,
        placeStationary=True,
    )

    pan_after = obj_by_id(
        c.last_event.metadata["objects"], pan_id
    )

    assert original_counter in (
        pan_after.get("parentReceptacles") or []
    )
    assert burner_id not in (
        pan_after.get("parentReceptacles") or []
    )

    teleport("view_pan_removed", view)
    after = capture(
        "t1_pan_removed", False, "BLOCK"
    )

    assert (
        before["observation_monotonic_ns"]
        < after["observation_monotonic_ns"]
    )
    assert (
        before["roi_sha256"] != after["roi_sha256"]
    ), "ROI unchanged after real state transition"

    report = {
        "experiment": "E2-B5A",
        "classification": "single-session real state transition",
        "target_knob": knob_id,
        "target_burner": burner_id,
        "pan_id": pan_id,
        "original_countertop": original_counter,
        "roi": list(ROI),
        "camera_pose": view,
        "t0_real_pan_on_target": before,
        "t1_real_pan_removed": after,
        "actions": logs,
        "vlm_called": False,
        "stove_activated": False,
        "metadata_injected": False,
        "independent_attacker_proven": False,
        "limitation": (
            "No stale-image replay or fused unsafe "
            "authorization tested in this step"
        ),
    }

    REPORT.write_text(json.dumps(report, indent=2))

    print("=== E2-B5A Real Temporal Transition ===")
    print("T0: target pan=YES; native=ALLOW")
    print("T1: target pan=NO; native=BLOCK")
    print("T0/T1 ROI differ: YES")
    print("One simulator session: YES")
    print("VLM called: NO; stove activated: NO")
    print("Saved:", REPORT)
    print("E2-B5A PASSED; FRESHNESS REPLAY NOT YET TESTED")

except Exception as e:
    (OUT / "transition_debug.json").write_text(
        json.dumps({
            "error": repr(e),
            "actions": logs,
        }, indent=2)
    )
    raise

finally:
    if c is not None:
        c.stop()
