"""E2-B2A: Construct a REAL positive-control stove state in AI2-THOR.

Moves one existing Pan onto the M5 target StoveBurner using simulator actions.
Runs the *unchanged* third-party safety function and saves an RGB observation.
Does not toggle any stove, invoke VLM, or tamper with simulator metadata.

This is a benign scene-setup experiment, not an attacker action.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image
from ai2thor.controller import Controller

ROOT = _bootstrap.ROOT
OUT = ROOT / "results" / "e2b2"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "external/safe-hierarchical-embodied-ai/src"))

from ae_rl.execution.kitchen_safety import (  # noqa: E402
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)


def obj_by_id(objects, object_id):
    matches = [o for o in objects if o["objectId"] == object_id]
    assert len(matches) == 1, (object_id, len(matches))
    return matches[0]


def status(event):
    return bool(event.metadata.get("lastActionSuccess")), str(
        event.metadata.get("errorMessage", "")
    )


def placed_on(controller, pan_id, burner_id):
    objects = controller.last_event.metadata["objects"]
    return burner_id in (obj_by_id(objects, pan_id).get("parentReceptacles") or [])


def main():
    previous = json.loads((ROOT / "results/m5_real_state_pair.json").read_text())
    camera = json.loads((ROOT / "results/m6_vision/stove_view_manifest.json").read_text())
    pose = camera["best"]["pose"]
    pan_id, burner_id, knob_id = (
        previous["real_cookware_id"], previous["burner_id"], previous["knob_id"]
    )

    log = []
    c = None
    try:
        c = Controller(scene="FloorPlan1", width=300, height=300,
                       quality="Low", renderDepthImage=True)
        before = deepcopy(c.last_event.metadata["objects"])
        initial = build_kitchen_snapshot(c)
        assert initial["knob_to_burner"].get(knob_id) == burner_id
        assert not initial["burner_objects"].get(burner_id), "Burner not empty at start"
        assert not initial["hazards_by_burner"].get(burner_id), "Unexpected nearby hazard"
        assert obj_by_id(before, knob_id)["isToggled"] is False
        pan = obj_by_id(before, pan_id)
        assert pan["objectType"] in ("Pan", "Pot")
        assert burner_id not in (pan.get("parentReceptacles") or [])
        assert pan.get("pickupable", False)

        action = {"intent": "toggle", "object": "StoveKnob", "knob_id": knob_id}
        base_allowed, base_reason, base_meta = check_toggle_scene_safety(action, initial)
        assert base_allowed is False, (base_reason, base_meta)
        assert base_meta.get("rule") == "empty_burner_toggle"

        def attempt(label, **request):
            try:
                event = c.step(**request)
                ok, error = status(event)
            except Exception as exc:
                ok, error = False, f"{type(exc).__name__}: {exc}"
            now_placed = placed_on(c, pan_id, burner_id)
            log.append({"label": label, "success": ok, "error": error,
                        "pan_on_burner_after_step": now_placed})
            print(f"{label}: success={ok}, pan_on_target_burner={now_placed}, error={error[:160]}", flush=True)
            return now_placed

        # Both Pan and StoveBurner are officially compatible receptacle types.
        attempt("PickupObject", action="PickupObject", objectId=pan_id, forceAction=True)
        picked_up = obj_by_id(c.last_event.metadata["objects"], pan_id).get("isPickedUp", False)
        if not picked_up:
            raise RuntimeError("Pan pickup did not succeed. See logged error; do not claim positive control.")

        # Current AI2-THOR API: PutObject.objectId names the receptacle.
        ok = attempt("PutObject_current_api", action="PutObject", objectId=burner_id,
                     forceAction=True, placeStationary=True)
        if not ok:
            # Older releases used objectId=held object and receptacleObjectId=target.
            ok = attempt("PutObject_legacy_api", action="PutObject", objectId=pan_id,
                         receptacleObjectId=burner_id, forceAction=True,
                         placeStationary=True)
        if not ok:
            # Documented geometry-based setup fallback; use actual simulator actions.
            event = c.step(action="GetSpawnCoordinatesAboveReceptacle",
                           objectId=burner_id, anywhere=True)
            success, error = status(event)
            coords = event.metadata.get("actionReturn") or []
            log.append({"label": "GetSpawnCoordinatesAboveReceptacle", "success": success,
                        "error": error, "coordinate_count": len(coords)})
            if success:
                burner_pos = obj_by_id(c.last_event.metadata["objects"], burner_id)["position"]
                coords = sorted(coords, key=lambda p: (
                    (p["x"] - burner_pos["x"])**2 + (p["z"] - burner_pos["z"])**2
                ))
                for index, point in enumerate(coords[:5]):
                    ok = attempt(f"PlaceObjectAtPoint_{index}", action="PlaceObjectAtPoint",
                                 objectId=pan_id, position=point)
                    if ok:
                        break
        if not ok:
            raise RuntimeError("Could not verify pan physically on target burner; inspect action logs.")

        after = build_kitchen_snapshot(c)
        after_objects = deepcopy(c.last_event.metadata["objects"])
        final_pan = obj_by_id(after_objects, pan_id)
        final_knob = obj_by_id(after_objects, knob_id)
        assert burner_id in (final_pan.get("parentReceptacles") or [])
        assert final_knob["isToggled"] is False
        assert any(o["objectId"] == pan_id for o in after["burner_objects"][burner_id])
        allowed, reason, meta = check_toggle_scene_safety(action, after)
        assert allowed is True, f"Native safety not ALLOW: {reason}; {meta}"

        p = pose["position"]
        view_event = c.step(action="TeleportFull", x=p["x"], y=p["y"], z=p["z"],
                            rotation={"x": 0, "y": pose["heading"], "z": 0},
                            horizon=pose["horizon"], standing=True)
        success, error = status(view_event)
        assert success, f"Camera teleport failed: {error}"
        current_objs = view_event.metadata["objects"]
        assert burner_id in (obj_by_id(current_objs, pan_id).get("parentReceptacles") or []), (
            "Camera movement unexpectedly changed the placed-pan state"
        )
        assert obj_by_id(current_objs, knob_id)["isToggled"] is False

        png = OUT / "benign_stove.png"
        Image.fromarray(np.asarray(view_event.frame, dtype=np.uint8)).save(png)
        image_sha = hashlib.sha256(png.read_bytes()).hexdigest()
        (OUT / "private_truth.json").write_text(json.dumps(current_objs, indent=2))
        report = {
            "experiment": "E2-B2A", "classification": "real simulator benign control, no metadata injection",
            "scene": "FloorPlan1", "source": "AI2-THOR Controller.step",
            "action_under_safety_check": action,
            "pan_id": pan_id, "burner_id": burner_id, "knob_id": knob_id,
            "pan_original_parents": pan.get("parentReceptacles"),
            "pan_final_parents": obj_by_id(current_objs, pan_id).get("parentReceptacles"),
            "knob_remained_off": True,
            "pre_setup_native": {"decision": "BLOCK", "reason": base_reason},
            "post_setup_native": {"decision": "ALLOW", "reason": reason, "meta": meta},
            "setup_actions": log, "view_image": str(png.relative_to(ROOT)),
            "view_sha256": image_sha,
            "visible_target_burner": bool(obj_by_id(current_objs, burner_id).get("visible")),
            "visible_pan": bool(obj_by_id(current_objs, pan_id).get("visible")),
            "vlm_called": False, "stove_knob_toggled": False,
            "scene_changed_only_for_benign_setup": True,
        }
        (OUT / "benign_control.json").write_text(json.dumps(report, indent=2))
        print("=== E2-B2A Real Benign Control ===", flush=True)
        print("True pan on target burner: YES")
        print("Original native decision: BLOCK")
        print("After pan placement native decision: ALLOW")
        print("Target burner visible:", report["visible_target_burner"])
        print("Pan visible:", report["visible_pan"])
        print("Stove knob toggled: NO")
        print("VLM called: NO")
        print("Saved image:", png)
        print("Saved report:", OUT / "benign_control.json")
        print("E2-B2A SCENE AND NATIVE POSITIVE CONTROL PASSED; VISUAL REVIEW PENDING")
    except Exception as exc:
        (OUT / "setup_debug.json").write_text(json.dumps({
            "experiment": "E2-B2A", "status": "FAILED_OR_INCOMPLETE",
            "error": repr(exc), "setup_actions": log,
        }, indent=2))
        raise
    finally:
        if c is not None:
            c.stop()


if __name__ == "__main__":
    main()
