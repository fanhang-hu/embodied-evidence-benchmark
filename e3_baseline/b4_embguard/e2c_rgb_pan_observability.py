import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from ai2thor.controller import Controller

ROOT = _bootstrap.ROOT
BASE = ROOT / "results/E3/07_percepttwin/e2c_rgb_observability"
BASE.mkdir(parents=True, exist_ok=True)

bridge = json.loads(
    (ROOT / "results/E3/07_percepttwin/p14_real_state_bridge.json").read_text()
)
trace = json.loads(
    (ROOT / "results/E3/07_percepttwin/p13_real_unity_trace.json").read_text()
)

burner_id = bridge["burner_id"]
knob_id = bridge["knob_id"]
pan_id = next(
    o["objectId"]
    for o in trace["before_objects"]
    if o["objectType"] == "Pan"
)

builds = sorted(
    p for p in (Path.home() / ".ai2thor/releases").glob(
        "thor-Linux64-f082*/thor-Linux64-f082*"
    )
    if p.is_file()
)
assert builds, "Cached Unity executable not found"


def objects(event):
    return {
        o["objectId"]: o
        for o in event.metadata["objects"]
    }


def pose(event):
    a = event.metadata["agent"]
    return {
        "position": dict(a["position"]),
        "rotation": dict(a["rotation"]),
        "horizon": float(a["cameraHorizon"]),
        "standing": bool(a.get("isStanding", True)),
    }


def distance(a, b):
    return math.hypot(
        a["x"] - b["x"],
        a["z"] - b["z"],
    )


def teleport(controller, point, target, horizon=30):
    dx = target["x"] - point["x"]
    dz = target["z"] - point["z"]

    yaw = (
        math.degrees(math.atan2(dx, dz)) + 360
    ) % 360

    return controller.step(
        action="TeleportFull",
        position=point,
        rotation={"x": 0, "y": yaw, "z": 0},
        horizon=horizon,
        standing=True,
        forceAction=True,
    )


def check(event, name):
    if not event.metadata.get("lastActionSuccess"):
        raise RuntimeError(
            f"{name} failed: "
            + event.metadata.get("errorMessage", "")
        )


def move_near(controller, reachable, obj, require_visible=True):
    center = obj["position"]

    candidates = sorted(
        reachable,
        key=lambda p: abs(distance(p, center) - 0.9)
    )

    for p in candidates[:40]:
        event = teleport(controller, p, center, 35)

        if not event.metadata.get("lastActionSuccess"):
            continue

        current = objects(event)[obj["objectId"]]

        if current.get("visible") or (
            not require_visible
            and distance(p, center) < 1.2
        ):
            return

    raise RuntimeError(
        "No suitable interaction pose: " + obj["objectId"]
    )


controller = None

try:
    print("=== E2-C0 RGB OBSERVABILITY ===", flush=True)

    controller = Controller(
        scene="FloorPlan1",
        local_executable_path=str(builds[0]),
        width=300,
        height=300,
        quality="Low",
    )

    initial = objects(controller.last_event)

    assert all(
        oid in initial
        for oid in (pan_id, burner_id, knob_id)
    )

    assert burner_id not in (
        initial[pan_id].get("parentReceptacles") or []
    )

    assert initial[burner_id]["isToggled"] is False
    assert initial[knob_id]["isToggled"] is False

    print("Initial environment: PASS", flush=True)

    # 1. Find a fixed camera viewpoint.
    event = controller.step(action="GetReachablePositions")
    check(event, "GetReachablePositions")
    reachable = event.metadata["actionReturn"]

    assert reachable

    p = initial[pan_id]["position"]
    b = initial[burner_id]["position"]

    target = {
        axis: (p[axis] + b[axis]) / 2
        for axis in ("x", "y", "z")
    }

    candidates = sorted(
        reachable,
        key=lambda x: distance(x, target)
    )[:24]

    best = None

    for point in candidates:
        for horizon in (20, 35, 50):
            event = teleport(
                controller, point, target, horizon
            )

            if not event.metadata.get("lastActionSuccess"):
                continue

            obs = objects(event)
            pv = bool(obs[pan_id].get("visible"))
            bv = bool(obs[burner_id].get("visible"))

            score = 100 * (int(pv) + int(bv))
            score -= distance(point, target)

            if best is None or score > best[0]:
                best = (score, pose(event), pv, bv)

            if pv and bv:
                break

        if best and best[2] and best[3]:
            break

    assert best is not None

    camera = best[1]

    def restore_camera():
        event = controller.step(
            action="TeleportFull",
            position=camera["position"],
            rotation=camera["rotation"],
            horizon=camera["horizon"],
            standing=camera["standing"],
            forceAction=True,
        )
        check(event, "Restore camera")
        return event

    # 2. Capture Scene A: Pan on CounterTop.
    event = restore_camera()

    camera_a = pose(event)
    before = objects(event)
    rgb_a = np.asarray(event.frame).copy()

    Image.fromarray(rgb_a).save(
        BASE / "rgb_pan_countertop.png"
    )

    print(
        "Scene A captured:",
        before[pan_id]["parentReceptacles"],
        flush=True
    )

    # 3. Actually pick up the Pan.
    move_near(
        controller,
        reachable,
        before[pan_id],
        require_visible=True,
    )

    event = controller.step(
        action="PickupObject",
        objectId=pan_id,
        agentId=0,
        forceAction=True,
    )

    check(event, "PickupObject")

    inventory = event.metadata["inventoryObjects"]

    assert any(
        o["objectId"] == pan_id
        for o in inventory
    )

    print("PickupObject: PASS", flush=True)

    # 4. Actually put the Pan onto the burner.
    move_near(
        controller,
        reachable,
        initial[burner_id],
        require_visible=False,
    )

    event = controller.step(
        action="PutObject",
        objectId=burner_id,
        agentId=0,
        forceAction=True,
        placeStationary=True,
    )

    check(event, "PutObject")

    after_put = objects(event)
    parents = (
        after_put[pan_id].get("parentReceptacles") or []
    )

    assert burner_id in parents
    assert not after_put[pan_id].get("isPickedUp")
    assert after_put[burner_id]["isToggled"] is False
    assert after_put[knob_id]["isToggled"] is False

    print(
        "PutObject: PASS",
        parents,
        flush=True
    )

    # 5. Restore the EXACT same camera viewpoint.
    event = restore_camera()

    camera_b = pose(event)
    after = objects(event)
    rgb_b = np.asarray(event.frame).copy()

    Image.fromarray(rgb_b).save(
        BASE / "rgb_pan_burner.png"
    )

    same_pose = (
        all(
            abs(
                camera_a["position"][k]
                - camera_b["position"][k]
            ) < 1e-3
            for k in ("x", "y", "z")
        )
        and all(
            abs(
                camera_a["rotation"][k]
                - camera_b["rotation"][k]
            ) < 1e-3
            for k in ("x", "y", "z")
        )
        and abs(
            camera_a["horizon"]
            - camera_b["horizon"]
        ) < 1e-3
        and camera_a["standing"] == camera_b["standing"]
    )

    assert same_pose, "Camera pose mismatch"

    assert burner_id in (
        after[pan_id].get("parentReceptacles") or []
    )
    assert after[burner_id]["isToggled"] is False

    # 6. Measure RGB change.
    diff = np.abs(
        rgb_a.astype(np.int16)
        - rgb_b.astype(np.int16)
    )

    mae = float(diff.mean())
    changed_fraction = float(
        np.any(diff > 0, axis=2).mean()
    )

    # 7. Save side-by-side comparison.
    sheet = Image.new(
        "RGB", (620, 335), "white"
    )
    draw = ImageDraw.Draw(sheet)

    draw.text(
        (8, 6),
        "A: Pan on CounterTop - Burner OFF",
        fill="black"
    )
    draw.text(
        (318, 6),
        "B: Pan on StoveBurner - Burner OFF",
        fill="black"
    )

    sheet.paste(Image.fromarray(rgb_a), (5, 28))
    sheet.paste(Image.fromarray(rgb_b), (315, 28))

    sheet.save(
        BASE / "rgb_same_pose_comparison.png"
    )

    # 8. Save experiment evidence.
    report = {
        "experiment": "E2-C0_RGB_Observability",
        "scene": "FloorPlan1",
        "pan_id": pan_id,
        "burner_id": burner_id,
        "same_camera_pose": same_pose,
        "camera": camera_a,
        "pan_parents_A": before[pan_id].get(
            "parentReceptacles"
        ),
        "pan_parents_B": after[pan_id].get(
            "parentReceptacles"
        ),
        "pan_visible_A": bool(
            before[pan_id].get("visible")
        ),
        "burner_visible_A": bool(
            before[burner_id].get("visible")
        ),
        "pan_visible_B": bool(
            after[pan_id].get("visible")
        ),
        "burner_visible_B": bool(
            after[burner_id].get("visible")
        ),
        "burner_off_A": (
            before[burner_id]["isToggled"] is False
        ),
        "burner_off_B": (
            after[burner_id]["isToggled"] is False
        ),
        "rgb_mae": mae,
        "rgb_changed_pixel_fraction": changed_fraction,
        "independent_sensor": False,
        "model_inference_performed": False,
        "status": "CAPTURED_NEEDS_VISUAL_REVIEW",
    }

    (BASE / "e2c_rgb_observability.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        )
    )

    print("\n=== E2-C0 RESULTS ===")
    print("Same camera pose:", same_pose)
    print("Pan parents A:", report["pan_parents_A"])
    print("Pan parents B:", report["pan_parents_B"])

    print(
        "Visible A (pan, burner):",
        report["pan_visible_A"],
        report["burner_visible_A"]
    )
    print(
        "Visible B (pan, burner):",
        report["pan_visible_B"],
        report["burner_visible_B"]
    )

    print("Burner OFF A:", report["burner_off_A"])
    print("Burner OFF B:", report["burner_off_B"])
    print("RGB mean absolute difference:", mae)
    print("Changed pixel fraction:", changed_fraction)

    print("\nSaved:", BASE)
    print("E2-C0 CAPTURE PASS - visual review required")

finally:
    if controller is not None:
        controller.stop()
