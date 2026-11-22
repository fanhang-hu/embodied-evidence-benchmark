import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import traceback
from pathlib import Path

from ai2thor.controller import Controller
from ai2thor.hooks.procedural_asset_hook import ProceduralAssetHookRunner

ROOT = _bootstrap.ROOT
BASE = ROOT / "results/E3/07_percepttwin"
SCENE_DIR = ROOT / "external/PerceptTwin/cleanplanner/planscenes/blocks"

COMMIT = "f0825767cd50d69f666c7f282e54abfe58f1e917"
BUILD = f"thor-Linux64-{COMMIT}"
EXE = Path.home() / ".ai2thor/releases" / BUILD / BUILD

BASE.mkdir(parents=True, exist_ok=True)

scene = json.loads((SCENE_DIR / "scene.json").read_text())
expected = {x["id"] for x in scene["objects"]}

result = {
    "test": "P6 cached Unity compatibility",
    "python_api": "8524eadda94df0ab2dbb2ef5a577e4d37c712897",
    "unity_build": COMMIT,
    "official_scene_unchanged": True,
    "original_full_pipeline": False,
    "passed": False,
}

print("=== PerceptTwin P6: Cached Unity Compatibility ===")
print("Unity exists:", EXE.is_file())
print("Expected scene objects:", sorted(expected))

controller = None

try:
    controller = Controller(
        local_executable_path=str(EXE),
        scene=scene,
        width=300,
        height=300,
        quality="Low",
        agentMode="default",
        makeAgentsVisible=False,
        runtime_asset_ids=[],
        action_hook_runner=ProceduralAssetHookRunner(
            asset_directory=str(SCENE_DIR / "concrete_assets"),
            target_dir=str(BASE / "p6_runtime_assets"),
            asset_symlink=True,
            load_file_in_unity=True,
            verbose=False,
        ),
    )

    event = controller.last_event
    metadata = event.metadata
    objects = metadata.get("objects", [])

    actual = {
        obj.get("objectId")
        for obj in objects
    }

    missing = sorted(expected - actual)

    result["last_action_success"] = metadata.get("lastActionSuccess")
    result["unity_object_count"] = len(objects)
    result["actual_object_ids"] = sorted(str(x) for x in actual)
    result["missing_expected_ids"] = missing
    result["error_message"] = metadata.get("errorMessage", "")
    result["passed"] = (
        metadata.get("lastActionSuccess", False)
        and not missing
    )

    print("Unity objects:", len(objects))
    print("Missing expected objects:", missing)
    print("Last action success:", result["last_action_success"])
    print("Error:", result["error_message"])

    if event.frame is not None:
        from PIL import Image
        out = BASE / "p6_scene_rgb.png"
        Image.fromarray(event.frame).save(out)
        print("Screenshot:", out)

except Exception as e:
    result["error_type"] = type(e).__name__
    result["error_message"] = str(e)
    print("ERROR:", repr(e))
    traceback.print_exc(limit=8)

finally:
    if controller is not None:
        try:
            controller.stop()
        except Exception as e:
            print("Cleanup warning:", repr(e))

    output = BASE / "p6_cached_unity.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print("Saved:", output)
    print("P6 PASS" if result["passed"] else "P6 BLOCKED")
