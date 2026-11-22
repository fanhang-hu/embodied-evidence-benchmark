import _bootstrap  # Workspace paths and historical cross-script imports.
import copy
import json
import traceback
from importlib.metadata import version
from pathlib import Path

from ai2thor.controller import Controller
from PIL import Image

ROOT = _bootstrap.ROOT
OUT = ROOT / "results/E3/07_percepttwin"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "p13_real_unity_trace.json"


def get_by_id(objects):
    return {
        x["objectId"]: x
        for x in objects if x.get("objectId")
    }


def save_frame(event, name):
    if event.frame is not None:
        Image.fromarray(event.frame).save(OUT / name)


record = {
    "experiment": "P13_real_AI2THOR_action",
    "scene": "FloorPlan1",
    "ai2thor_version": version("ai2thor"),
    "runtime": "AI2-THOR Unity Player with CPU rendering",
    "action_origin": "direct simulator probe",
    "forceAction": True,
    "percepttwin_planner_executed": False,
    "status": "STARTED",
}

controller = None

try:
    print("Launching FloorPlan1 on CPU...", flush=True)

    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
    )

    before_event = controller.last_event
    before_objects = copy.deepcopy(
        before_event.metadata["objects"]
    )

    knobs = sorted(
        (
            o for o in before_objects
            if o.get("objectType") == "StoveKnob"
            and o.get("toggleable")
            and not o.get("isToggled")
        ),
        key=lambda o: o["objectId"],
    )

    record["available_off_knobs"] = [
        o["objectId"] for o in knobs
    ]

    print("Available off StoveKnobs:", len(knobs))

    if not knobs:
        raise RuntimeError(
            "No off StoveKnob found in FloorPlan1"
        )

    target = knobs[0]["objectId"]
    record["target_object_id"] = target
    record["before_objects"] = before_objects

    save_frame(before_event, "p13_before.png")

    print("Executing ToggleObjectOn:", target, flush=True)

    after_event = controller.step(
        action="ToggleObjectOn",
        objectId=target,
        forceAction=True,
    )

    after_objects = copy.deepcopy(
        after_event.metadata["objects"]
    )

    save_frame(after_event, "p13_after.png")

    before_map = get_by_id(before_objects)
    after_map = get_by_id(after_objects)

    changes = []

    for oid, old in before_map.items():
        new = after_map.get(oid)

        if (
            new is not None
            and old.get("isToggled") != new.get("isToggled")
        ):
            changes.append({
                "objectId": oid,
                "objectType": new.get("objectType"),
                "before_isToggled": old.get("isToggled"),
                "after_isToggled": new.get("isToggled"),
            })

    burner_changes = [
        x for x in changes
        if x["objectType"] == "StoveBurner"
    ]

    success = bool(
        after_event.metadata.get("lastActionSuccess")
    )

    knob_transition = (
        before_map[target].get("isToggled") is False
        and after_map[target].get("isToggled") is True
    )

    record.update({
        "action": {
            "action": "ToggleObjectOn",
            "objectId": target,
            "forceAction": True,
        },
        "lastActionSuccess": success,
        "errorMessage": after_event.metadata.get(
            "errorMessage", ""
        ),
        "after_objects": after_objects,
        "changed_toggle_objects": changes,
        "burner_changes": burner_changes,
        "knob_off_to_on": knob_transition,
        "status": (
            "PASS"
            if success and knob_transition and burner_changes
            else "PARTIAL"
        ),
    })

    print("lastActionSuccess:", success)
    print("Knob OFF -> ON:", knob_transition)
    print("Changed burners:", len(burner_changes))
    print("Changed objects:")
    print(json.dumps(changes, indent=2))

except Exception as exc:
    record["status"] = "ERROR"
    record["error"] = repr(exc)
    traceback.print_exc()

finally:
    if controller is not None:
        try:
            controller.stop()
        except Exception as exc:
            record["stop_warning"] = repr(exc)

    REPORT.write_text(
        json.dumps(record, indent=2, default=str)
    )

    print("Saved:", REPORT)
    print("P13:", record["status"])
