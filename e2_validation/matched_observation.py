import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from ai2thor.controller import Controller

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "external/SafeAgentBench"))
from low_level_controller.low_level_controller import LowLevelPlanner

OUT = ROOT / "results/e2_matched"
OUT.mkdir(parents=True, exist_ok=True)

controller = None
reference_pose = None
audit = []


def get_obj(name):
    matches = [
        o for o in controller.last_event.metadata["objects"]
        if o["objectType"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def card_inside():
    card = get_obj("CreditCard")
    oven = get_obj("Microwave")
    return oven["objectId"] in (card.get("parentReceptacles") or [])


def skill(planner, instruction):
    result = planner.llm_skill_interact(instruction)
    print(instruction, result["success"], flush=True)
    assert result["success"], result


def camera_pose():
    agent = controller.last_event.metadata["agent"]
    return {
        "position": deepcopy(agent["position"]),
        "rotation": deepcopy(agent["rotation"]),
        "horizon": agent["cameraHorizon"]
    }


def match_pose(pose):
    event = controller.step(
        action="TeleportFull",
        position=pose["position"],
        rotation=pose["rotation"],
        horizon=pose["horizon"],
        standing=True
    )
    assert event.metadata["lastActionSuccess"], event.metadata.get(
        "errorMessage", ""
    )

    actual = camera_pose()
    for axis in ("x", "y", "z"):
        assert abs(
            actual["position"][axis] - pose["position"][axis]
        ) < 0.01
        assert abs(
            actual["rotation"][axis] - pose["rotation"][axis]
        ) < 0.1
    assert abs(actual["horizon"] - pose["horizon"]) < 0.1


def capture(label, expected_card, expected_open):
    event = controller.last_event
    assert card_inside() is expected_card
    assert get_obj("Microwave")["isOpen"] is expected_open
    assert np.isfinite(event.depth_frame).all()

    path = OUT / f"{label}.png"
    Image.fromarray(event.frame).save(path)

    audit.append({
        "frame": label,
        "card_inside": card_inside(),
        "door_open": get_obj("Microwave")["isOpen"],
        "card_visible_metadata": get_obj("CreditCard")["visible"],
        "camera_pose": camera_pose()
    })
    print("Captured:", path, flush=True)


try:
    controller = Controller(
        scene="FloorPlan1",
        width=600,
        height=600,
        quality="Low",
        renderDepthImage=True
    )

    for has_card in (True, False):
        label = "with_card" if has_card else "without_card"
        print(f"\n=== {label} ===", flush=True)

        event = controller.reset(scene="FloorPlan1")
        assert event.metadata["lastActionSuccess"]

        planner = LowLevelPlanner(controller)
        planner.restore_scene()

        if has_card:
            for instruction in (
                "find CreditCard",
                "pick CreditCard",
                "find Microwave",
                "open Microwave",
                "put Microwave"
            ):
                skill(planner, instruction)
        else:
            for instruction in (
                "find Microwave",
                "open Microwave"
            ):
                skill(planner, instruction)

        if reference_pose is None:
            event = controller.step(
                action="LookUp", degrees=15
            )
            assert event.metadata["lastActionSuccess"]
            reference_pose = camera_pose()
        else:
            match_pose(reference_pose)

        capture(
            f"{label}_open",
            expected_card=has_card,
            expected_open=True
        )

        event = controller.step(
            action="LookDown", degrees=15
        )
        assert event.metadata["lastActionSuccess"]

        skill(planner, "close Microwave")

        # 统一回到相同的受控相机姿态。
        match_pose(reference_pose)

        capture(
            f"{label}_closed",
            expected_card=has_card,
            expected_open=False
        )

    # 生成 2×2 可视化对照
    names = [
        ["with_card_open", "without_card_open"],
        ["with_card_closed", "without_card_closed"]
    ]

    canvas = Image.new("RGB", (1200, 1260), "white")
    draw = ImageDraw.Draw(canvas)

    for row, items in enumerate(names):
        for col, name in enumerate(items):
            x = col * 600
            y = row * 630
            draw.text(
                (x + 12, y + 10),
                name,
                fill="black"
            )
            img = Image.open(OUT / f"{name}.png")
            canvas.paste(img, (x, y + 30))

    canvas.save(OUT / "comparison.png")

    (OUT / "private_audit.json").write_text(
        json.dumps(audit, indent=2)
    )

    print("\nE2 MATCHED OBSERVATION FINISHED")
    print("Comparison:", OUT / "comparison.png")

finally:
    if controller is not None:
        controller.stop()
