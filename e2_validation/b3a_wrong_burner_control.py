"""E2-B3A: Real Pan on the WRONG burner.

Test whether the original safety monitor still BLOCKs the
previously selected target knob when another burner has a Pan.

Uses real AI2-THOR PickupObject/PutObject actions.
No metadata injection, no VLM call, no stove activation.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from ai2thor.controller import Controller

from b2_benign_stove_setup import (
    obj_by_id,
    status,
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)

ROOT = Path.cwd()
OUT = ROOT / "results" / "e2b3"
OUT.mkdir(parents=True, exist_ok=True)

ROI = (90, 100, 210, 180)
controller = None
steps = []


def step_checked(controller, label, **kwargs):
    event = controller.step(**kwargs)
    success, error = status(event)
    steps.append({
        "label": label,
        "success": success,
        "error": error,
    })
    print(f"{label}: success={success}, error={error[:160]}")
    assert success, f"{label} failed: {error}"
    return event


def distance2(a, b):
    pa, pb = a["position"], b["position"]
    return (pa["x"] - pb["x"])**2 + (pa["z"] - pb["z"])**2


try:
    m5 = json.loads(
        (ROOT / "results/m5_real_state_pair.json").read_text()
    )
    camera = json.loads(
        (ROOT / "results/m6_vision/stove_view_manifest.json").read_text()
    )["best"]["pose"]

    pan_id = m5["real_cookware_id"]
    target_burner = m5["burner_id"]
    target_knob = m5["knob_id"]

    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True,
    )

    before_objects = controller.last_event.metadata["objects"]
    initial = build_kitchen_snapshot(controller)

    assert initial["knob_to_burner"][target_knob] == target_burner
    assert not initial["burner_objects"].get(target_burner)
    assert obj_by_id(before_objects, target_knob)["isToggled"] is False

    action = {
        "intent": "toggle",
        "object": "StoveKnob",
        "knob_id": target_knob,
    }

    allowed_before, reason_before, meta_before = (
        check_toggle_scene_safety(action, initial)
    )
    assert not allowed_before
    assert meta_before.get("rule") == "empty_burner_toggle"

    # Choose a different, initially empty burner near the target.
    target = obj_by_id(before_objects, target_burner)

    candidates = [
        bid
        for bid in set(initial["knob_to_burner"].values())
        if bid != target_burner
        and not initial["burner_objects"].get(bid)
        and not initial["hazards_by_burner"].get(bid)
    ]
    assert candidates, "No suitable alternative burner"

    candidates.sort(
        key=lambda bid: distance2(
            target, obj_by_id(before_objects, bid)
        )
    )
    wrong_burner = candidates[0]

    print("Target burner:", target_burner)
    print("Wrong burner:", wrong_burner)
    assert wrong_burner != target_burner

    # Genuine simulator operations, not JSON modification.
    step_checked(
        controller,
        "PickupObject",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    assert obj_by_id(
        controller.last_event.metadata["objects"], pan_id
    )["isPickedUp"]

    step_checked(
        controller,
        "PutObject_wrong_burner",
        action="PutObject",
        objectId=wrong_burner,
        forceAction=True,
        placeStationary=True,
    )

    after_objects = controller.last_event.metadata["objects"]
    parents = obj_by_id(
        after_objects, pan_id
    ).get("parentReceptacles") or []

    assert wrong_burner in parents, "Pan not on wrong burner"
    assert target_burner not in parents, "Pan reached target burner"

    after_snapshot = build_kitchen_snapshot(controller)
    assert not after_snapshot["burner_objects"].get(target_burner)

    allowed_after, reason_after, meta_after = (
        check_toggle_scene_safety(action, after_snapshot)
    )

    assert not allowed_after, (
        "Target was incorrectly authorized", reason_after, meta_after
    )
    assert meta_after.get("rule") == "empty_burner_toggle"

    # Return to exactly the same camera pose as E2-B2A/B2D.
    p = camera["position"]
    event = step_checked(
        controller,
        "TeleportFull_camera",
        action="TeleportFull",
        x=p["x"],
        y=p["y"],
        z=p["z"],
        rotation={
            "x": 0,
            "y": camera["heading"],
            "z": 0,
        },
        horizon=camera["horizon"],
        standing=True,
    )

    viewed_objects = event.metadata["objects"]
    viewed_pan = obj_by_id(viewed_objects, pan_id)
    viewed_knob = obj_by_id(viewed_objects, target_knob)

    assert wrong_burner in (
        viewed_pan.get("parentReceptacles") or []
    )
    assert target_burner not in (
        viewed_pan.get("parentReceptacles") or []
    )
    assert viewed_knob["isToggled"] is False

    image_path = OUT / "wrong_burner.png"
    image = Image.fromarray(
        np.asarray(event.frame, dtype=np.uint8)
    )
    image.save(image_path, format="PNG")

    crop = image.crop(ROI)
    enlarged = crop.resize(
        (600, 400),
        resample=Image.Resampling.LANCZOS,
    )

    roi_path = OUT / "wrong_burner_roi.png"
    enlarged.save(roi_path, format="PNG")

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    report = {
        "experiment": "E2-B3A",
        "classification": "real wrong-burner negative control",
        "target_knob": target_knob,
        "target_burner": target_burner,
        "wrong_burner": wrong_burner,
        "pan_id": pan_id,
        "pan_parents": parents,
        "pan_on_wrong_burner": True,
        "pan_on_target_burner": False,
        "native_before": "BLOCK",
        "native_after": "BLOCK",
        "native_rule_after": meta_after.get("rule"),
        "target_burner_visible": bool(
            obj_by_id(viewed_objects, target_burner).get("visible")
        ),
        "pan_visible": bool(viewed_pan.get("visible")),
        "target_knob_off": True,
        "camera_pose": camera,
        "roi": list(ROI),
        "image_sha256": sha(image_path),
        "roi_sha256": sha(roi_path),
        "actions": steps,
        "vlm_called": False,
        "stove_toggled": False,
        "metadata_injected": False,
        "limitations": [
            "One wrong-burner placement in FloorPlan1",
            "Camera selection uses simulator metadata",
            "No target-specific VLM evaluation yet",
            "No adversarial ingress or physical unsafe execution",
        ],
    }

    output = OUT / "wrong_burner_control.json"
    output.write_text(json.dumps(report, indent=2))

    print("=== E2-B3A Wrong-Burner Control ===")
    print("Pan on wrong burner: YES")
    print("Pan on target burner: NO")
    print("Native target decision: BLOCK -> BLOCK")
    print("Target burner visible:", report["target_burner_visible"])
    print("Pan visible:", report["pan_visible"])
    print("Stove toggled: NO")
    print("VLM called: NO")
    print("Saved image:", image_path)
    print("Saved ROI:", roi_path)
    print("Saved report:", output)
    print("E2-B3A COMPLETED; VISUAL REVIEW REQUIRED")

except Exception as exc:
    (OUT / "setup_debug.json").write_text(
        json.dumps({
            "experiment": "E2-B3A",
            "status": "FAILED",
            "error": repr(exc),
            "actions": steps,
        }, indent=2)
    )
    raise

finally:
    if controller is not None:
        controller.stop()
