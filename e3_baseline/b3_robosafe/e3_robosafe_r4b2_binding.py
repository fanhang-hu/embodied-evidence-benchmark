import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path
from PIL import Image, ImageDraw
from ai2thor.controller import Controller

ROOT = Path("results/E3/05_optional/robosafe")
SRC = ROOT / "r4a_targeted_views_v1/manifest.json"
OUT = ROOT / "r4b2_binding_v1"

assert SRC.is_file()
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

manifest = json.loads(SRC.read_text())
OUT.mkdir(parents=True)

sheet = Image.new("RGB", (960, 680), "white")
draw_sheet = ImageDraw.Draw(sheet)
report = []
controller = None

try:
    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
        renderInstanceSegmentation=True,
    )

    for scene_i, spec in enumerate(manifest["scenes"]):
        scene = spec["scene"]

        if scene_i:
            controller.reset(scene=scene)

        folder = OUT / scene
        folder.mkdir()

        records = []

        for i, view in enumerate(spec["best_views"][:3]):
            p = view["camera_position"]

            event = controller.step(
                action="TeleportFull",
                x=p["x"], y=p["y"], z=p["z"],
                rotation={
                    "x": 0,
                    "y": view["yaw"],
                    "z": 0,
                },
                horizon=view["horizon"],
                standing=True,
            )

            assert event.metadata["lastActionSuccess"], (
                scene, i, event.metadata.get("errorMessage")
            )

            detections = event.instance_detections2D
            assert detections is not None, (
                "Instance segmentation unavailable"
            )

            knob = spec["knob_id"]
            burner = spec["burner_id"]

            knob_box = (
                list(map(int, detections[knob]))
                if knob in detections else None
            )
            burner_box = (
                list(map(int, detections[burner]))
                if burner in detections else None
            )

            original = Image.fromarray(event.frame)
            annotated = original.copy()
            draw = ImageDraw.Draw(annotated)

            if burner_box:
                draw.rectangle(
                    burner_box,
                    outline=(220, 40, 40),
                    width=4,
                )

            if knob_box:
                draw.rectangle(
                    knob_box,
                    outline=(40, 80, 220),
                    width=3,
                )

            original_path = folder / f"original_{i}.png"
            marked_path = folder / f"marked_{i}.png"

            original.save(original_path)
            annotated.save(marked_path)

            valid_binding = (
                burner_box is not None
                and knob_box is not None
            )

            record = {
                "scene": scene,
                "view_rank": i,
                "original_image": str(original_path),
                "marked_image": str(marked_path),
                "target_burner_box": burner_box,
                "candidate_knob_box": knob_box,
                "target_binding_overlay_available":
                    valid_binding,
                "occupancy_label_supplied": False,
                "annotation_source":
                    "simulator_instance_segmentation",
                "independent_visual_grounding": False,
            }

            records.append(record)

            x = i * 320 + 10
            y = scene_i * 340 + 30

            sheet.paste(annotated, (x, y))
            draw_sheet.text(
                (x, y - 19),
                f"{scene} | view {i} | binding={valid_binding}",
                fill="black",
            )

            print(
                scene, "view=", i,
                "burner_bbox=", burner_box,
                "knob_bbox=", knob_box,
                "binding_available=", valid_binding,
            )

        report.append({
            "scene": scene,
            "views": records,
        })

    sheet.save(OUT / "contact_sheet.png")

    result = {
        "experiment": "RoboSafe-R4B2",
        "implementation": "simulator_assisted_target_binding",
        "official_robosafe": False,
        "model_calls": 0,
        "unsafe_actions_executed": False,
        "target_metadata_used_for_annotation": True,
        "occupancy_truth_given_to_model": False,
        "independent_binding_proven": False,
        "scenes": report,
    }

    (OUT / "manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )

    print("\n=== ROBOSAFE-R4B2 SUMMARY ===")
    for item in report:
        n = sum(
            x["target_binding_overlay_available"]
            for x in item["views"]
        )
        print(item["scene"], "complete target boxes:", n)

    print("Saved:", OUT / "contact_sheet.png")
    print("ROBOSAFE-R4B2 COMPLETED")

finally:
    if controller is not None:
        controller.stop()
