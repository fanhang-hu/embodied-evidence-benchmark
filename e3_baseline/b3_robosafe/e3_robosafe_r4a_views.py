import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw
from ai2thor.controller import Controller

ROOT = Path("results/E3/05_optional/robosafe")
OUT = ROOT / "r4a_targeted_views_v1"
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

e3b3 = json.loads(
    Path("results/E3/04_contract/e3b3_native_controller_guard.json").read_text()
)
m3 = json.loads(
    (ROOT.parent / "04_contract/safegate/m3_benign_pairs.json").read_text()
) if False else json.loads(
    Path("results/E3/04_contract/safegate/m3_benign_pairs.json").read_text()
)

f4 = next(x for x in m3["cases"] if x["scene"] == "FloorPlan4")

SPECS = [
    ("FloorPlan1", e3b3["target_knob"], e3b3["target_burner"]),
    ("FloorPlan4", f4["knob_id"], f4["burner_id"]),
]

OUT.mkdir(parents=True)
report = []
controller = None
sheet = Image.new("RGB", (960, 680), "white")
draw = ImageDraw.Draw(sheet)

try:
    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
    )

    for scene_index, (scene, knob_id, burner_id) in enumerate(SPECS):
        if scene_index:
            controller.reset(scene=scene)

        objects = controller.last_event.metadata["objects"]
        by_id = {o["objectId"]: o for o in objects}
        assert knob_id in by_id and burner_id in by_id

        bp = by_id[burner_id]["position"]
        cookware_ids = [
            o["objectId"] for o in objects
            if o.get("objectType") in ("Pan", "Pot")
            and burner_id in (o.get("parentReceptacles") or [])
        ]

        event = controller.step(action="GetReachablePositions")
        assert event.metadata["lastActionSuccess"]
        positions = event.metadata["actionReturn"]

        sectors = {}
        for p in positions:
            dx = p["x"] - bp["x"]
            dz = p["z"] - bp["z"]
            distance = math.hypot(dx, dz)
            if not 0.65 <= distance <= 2.5:
                continue
            angle = (math.degrees(math.atan2(dx, dz)) + 360) % 360
            sector = int(angle // 45)
            sectors.setdefault(sector, []).append(
                (abs(distance - 1.3), p)
            )

        candidates = []
        for sector in sorted(sectors):
            choices = sorted(sectors[sector], key=lambda x: x[0])
            candidates.extend(p for _, p in choices[:2])
        candidates = candidates[:12]

        assert candidates, f"No reachable camera positions: {scene}"

        folder = OUT / scene
        folder.mkdir()
        records = []

        for i, p in enumerate(candidates):
            yaw = (
                math.degrees(
                    math.atan2(bp["x"] - p["x"], bp["z"] - p["z"])
                ) + 360
            ) % 360

            event = controller.step(
                action="TeleportFull",
                x=p["x"], y=p["y"], z=p["z"],
                rotation={"x": 0, "y": yaw, "z": 0},
                horizon=30,
                standing=True,
            )

            if not event.metadata.get("lastActionSuccess", False):
                print(scene, i, "TELEPORT_FAILED",
                      event.metadata.get("errorMessage", ""))
                continue

            current = {
                o["objectId"]: o
                for o in event.metadata["objects"]
            }

            burner_vis = bool(current[burner_id].get("visible"))
            knob_vis = bool(current[knob_id].get("visible"))
            cookware_vis = [
                bool(current[c].get("visible", False))
                for c in cookware_ids
            ]

            path = folder / f"view_{i:02d}.png"
            Image.fromarray(event.frame).save(path)

            score = (
                2 * int(burner_vis)
                + int(knob_vis)
                + sum(cookware_vis)
            )

            record = {
                "image": str(path),
                "camera_position": p,
                "yaw": yaw,
                "horizon": 30,
                "burner_visible_metadata": burner_vis,
                "knob_visible_metadata": knob_vis,
                "cookware_visible_metadata": cookware_vis,
                "selection_score": score,
                "target_roi_verified": False,
                "independent_visual_grounding_verified": False,
            }

            records.append(record)

            print(scene, i,
                  "burner=", burner_vis,
                  "knob=", knob_vis,
                  "cookware=", cookware_vis,
                  "score=", score)

        ranked = sorted(
            records,
            key=lambda r: r["selection_score"],
            reverse=True,
        )

        for j, record in enumerate(ranked[:3]):
            img = Image.open(record["image"]).convert("RGB")
            x = j * 320 + 10
            y = scene_index * 340 + 30
            sheet.paste(img, (x, y))
            draw.text(
                (x, y - 20),
                f"{scene} | rank {j+1} | score {record['selection_score']}",
                fill="black",
            )

        report.append({
            "scene": scene,
            "knob_id": knob_id,
            "burner_id": burner_id,
            "cookware_ids": cookware_ids,
            "capture_count": len(records),
            "records": records,
            "best_views": ranked[:3],
        })

    sheet_path = OUT / "contact_sheet.png"
    sheet.save(sheet_path)

    summary = {
        "experiment": "RoboSafe-R4A",
        "purpose": "target_directed_visual_acquisition",
        "official_robosafe_reproduced": False,
        "model_calls": 0,
        "unsafe_actions_executed": False,
        "metadata_used_only_for_view_selection": True,
        "visual_grounding_independently_verified": False,
        "scenes": report,
    }

    (OUT / "manifest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )

    print("\n=== ROBOSAFE-R4A SUMMARY ===")
    for item in report:
        print(
            item["scene"],
            "frames=", item["capture_count"],
            "best_scores=",
            [x["selection_score"] for x in item["best_views"]],
        )
    print("Contact sheet:", sheet_path)
    print("Unsafe actions executed: NO")
    print("ROBOSAFE-R4A CAPTURE COMPLETE")

finally:
    if controller is not None:
        controller.stop()
