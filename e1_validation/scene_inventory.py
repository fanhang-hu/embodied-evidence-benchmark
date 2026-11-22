import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path
from ai2thor.controller import Controller

SCENE = "FloorPlan1"
OUT = Path("results/m1_scene_catalogue.json")
OUT.parent.mkdir(exist_ok=True)

controller = None

try:
    controller = Controller(
        scene=SCENE,
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    objects = controller.last_event.metadata["objects"]

    catalogue = {
        "role": "private_offline_catalogue",
        "scene": SCENE,
        "objects": []
    }

    for obj in objects:
        record = {
            "objectId": obj["objectId"],
            "objectType": obj["objectType"],
            "openable": obj.get("openable"),
            "isOpen": obj.get("isOpen"),
            "toggleable": obj.get("toggleable"),
            "isToggled": obj.get("isToggled"),
            "visible": obj.get("visible"),
            "position": obj.get("position"),
            "receptacleObjectIds": obj.get("receptacleObjectIds"),
            "parentReceptacles": obj.get("parentReceptacles")
        }
        catalogue["objects"].append(record)

    print("Scene:", SCENE)
    print("Total objects:", len(objects))

    targets = {
        "Microwave", "StoveBurner", "StoveKnob",
        "Kettle", "Cabinet", "Fridge"
    }

    print("\n=== Safety-Relevant Objects ===")

    for obj in catalogue["objects"]:
        if obj["objectType"] in targets:
            print(json.dumps(obj, indent=2))

    with OUT.open("w") as f:
        json.dump(catalogue, f, indent=2)

    print("\nPrivate catalogue saved:", OUT)
    print("SCENE INSPECTION FINISHED")

finally:
    if controller is not None:
        controller.stop()
