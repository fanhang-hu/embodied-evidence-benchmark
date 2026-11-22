import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

ROOT = Path("external/PerceptTwin")
SCENES = ROOT / "cleanplanner/planscenes"

print("=== PerceptTwin P1: Native Runtime Preflight ===")
print("Python:", sys.version.split()[0])

print("\n[1] Required packages")

packages = [
    "ai2thor",
    "numpy",
    "torch",
    "jax",
    "jaxlib",
    "open3d",
    "hydra-core",
    "omegaconf",
    "diskcache",
    "wandb",
    "ai2holodeck",
]

for name in packages:
    try:
        print(f"{name:16} {version(name)}")
    except PackageNotFoundError:
        print(f"{name:16} NOT INSTALLED")

print("\n[2] Official scene JSON files")

for path in sorted(SCENES.glob("*/scene.json")):
    try:
        scene = json.loads(path.read_text())
        objects = scene.get("objects", [])
        print(f"SCENE: {path}")
        print(f"Objects: {len(objects)}")
        print(
            "Names:",
            [x.get("object_name") for x in objects]
        )
    except Exception as e:
        print("SCENE ERROR:", path, repr(e))

print("\n[3] Default scene resolution")

default_scene = SCENES / "knife/scene.json"
print("Default knife scene exists:", default_scene.is_file())

print("\n[4] Official feedback configurations")

for name in [
    "conditiononly",
    "audits_and_conditions_with_task",
    "audits_and_conditions_without_task",
]:
    path = ROOT / f"cleanplanner/config/feedback/{name}.yaml"
    print(f"\n{name}:")
    print(path.read_text() if path.exists() else "MISSING")

print("\n[5] ConceptGraphs dataset completeness")

for name in ["sacha_kitchen", "sacha_kitchen_knife"]:
    p = ROOT / "hippo/datasets" / name
    required = [
        "segments_anno.json",
        "clip_features.npy",
        "point_cloud.pcd",
    ]
    print(name, {
        x: (p / x).is_file() for x in required
    })

print("\nPERCEPTTWIN P1 PREFLIGHT COMPLETE")
