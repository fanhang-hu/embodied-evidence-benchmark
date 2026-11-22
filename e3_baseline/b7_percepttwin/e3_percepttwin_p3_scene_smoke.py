import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import traceback
from pathlib import Path

from ai2thor.controller import Controller
from ai2thor.hooks.procedural_asset_hook import ProceduralAssetHookRunner

BASE = Path("results/E3/07_percepttwin")
SCENE_DIR = Path(
    "external/PerceptTwin/cleanplanner/planscenes/blocks"
).resolve()

SCENE_FILE = SCENE_DIR / "scene.json"
ASSET_DIR = SCENE_DIR / "concrete_assets"
OUT = BASE / "p3_scene_smoke.json"

scene = json.loads(SCENE_FILE.read_text())

expected_ids = [
    obj["assetId"]
    for obj in scene["objects"]
]

print("=== PerceptTwin P3: Native Scene Compatibility ===")
print("Scene:", SCENE_FILE)
print("Assets:", ASSET_DIR)
print("Expected objects:", len(expected_ids))

controller = None

result = {
    "experiment": "PerceptTwin-P3",
    "mode": "adapted_ai2thor_5_compatibility",
    "official_scene_unchanged": True,
    "official_verification_executed": False,
    "expected_objects": expected_ids,
    "scene_loaded": False,
}

try:
    controller = Controller(
        scene=scene,
        width=300,
        height=300,
        quality="Low",
        agentMode="default",
        makeAgentsVisible=False,
        action_hook_runner=ProceduralAssetHookRunner(
            asset_directory=str(ASSET_DIR),
            asset_symlink=True,
            verbose=False,
            load_file_in_unity=True,
        ),
    )

    event = controller.last_event
    metadata = event.metadata

    result["last_action_success"] = metadata.get(
        "lastActionSuccess"
    )
    result["error_message"] = metadata.get(
        "errorMessage", ""
    )

    objects = metadata.get("objects", [])
    result["unity_object_count"] = len(objects)
    result["unity_object_ids"] = [
        obj.get("objectId")
        for obj in objects
    ]

    result["scene_loaded"] = (
        metadata.get("lastActionSuccess", False)
        and len(objects) > 0
    )

    print("Last action success:",
          result["last_action_success"])
    print("Unity objects:", len(objects))
    print("Error:", result["error_message"])
    print("Scene loaded:", result["scene_loaded"])

except Exception as e:
    result["error_type"] = type(e).__name__
    result["error_message"] = str(e)
    print("SCENE_LOAD_ERROR:", repr(e))
    traceback.print_exc(limit=5)

finally:
    if controller is not None:
        try:
            controller.stop()
        except Exception as e:
            print("Cleanup warning:", repr(e))

    BASE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )

    print("Saved:", OUT)
    print(
        "PERCEPTTWIN P3 PASS"
        if result["scene_loaded"]
        else "PERCEPTTWIN P3 BLOCKED"
    )
