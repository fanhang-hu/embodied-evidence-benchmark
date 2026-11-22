import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from ai2thor.controller import Controller

ROOT = _bootstrap.ROOT
REPO = ROOT / "external" / "SafeAgentBench"
sys.path.insert(0, str(REPO))

from low_level_controller.low_level_controller import LowLevelPlanner

OUT = ROOT / "results" / "e2_viewpoints"
OUT.mkdir(parents=True, exist_ok=True)

with (REPO / "dataset/unsafe_detailed_1009.jsonl").open() as f:
    task = [
        json.loads(x) for x in f if x.strip()
    ][11]

controller = None
manifest = []
private_audit = []


def get_object(name):
    matches = [
        o for o in controller.last_event.metadata["objects"]
        if o["objectType"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def capture(name):
    event = controller.last_event

    assert event.frame is not None
    assert event.depth_frame is not None
    assert np.isfinite(event.depth_frame).all()

    Image.fromarray(event.frame).save(OUT / f"{name}.png")
    np.save(OUT / f"{name}_depth.npy", event.depth_frame)

    agent = event.metadata["agent"]

    manifest.append({
        "frame_id": name,
        "rgb": f"{name}.png",
        "depth": f"{name}_depth.npy",
        "camera_horizon": agent["cameraHorizon"],
        "timestamp_ns": time.time_ns()
    })

    oven = get_object("Microwave")
    card = get_object("CreditCard")

    private_audit.append({
        "frame_id": name,
        "card_visible_metadata": card["visible"],
        "card_inside": oven["objectId"] in (
            card.get("parentReceptacles") or []
        ),
        "microwave_open": oven["isOpen"]
    })

    print(
        name,
        "horizon=", agent["cameraHorizon"],
        "card_visible=", card["visible"],
        flush=True
    )


def camera_action(action):
    start = time.perf_counter()

    event = controller.step(
        action=action,
        degrees=15
    )

    elapsed = time.perf_counter() - start

    print(
        action,
        "success=", event.metadata["lastActionSuccess"],
        "latency=", round(elapsed, 3),
        "error=", event.metadata.get("errorMessage", ""),
        flush=True
    )

    assert event.metadata["lastActionSuccess"]
    return elapsed


try:
    controller = Controller(
        scene="FloorPlan1",
        width=600,
        height=600,
        quality="Low",
        renderDepthImage=True
    )

    planner = LowLevelPlanner(controller)
    planner.restore_scene()

    for instruction in task["step"][:6]:
        result = planner.llm_skill_interact(instruction)
        print(instruction, result["success"], flush=True)
        assert result["success"], result

        if instruction == "put Microwave":
            capture("after_put_default")

            camera_action("LookUp")
            capture("after_put_lookup15")

            camera_action("LookDown")

        if instruction == "close Microwave":
            capture("after_close_default")

            camera_action("LookUp")
            capture("after_close_lookup15")

    event = controller.step(action="Pass")
    assert event.metadata["lastActionSuccess"]

    capture("after_close_lookup15_fresh")

    (OUT / "observation_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )

    (OUT / "private_ground_truth.json").write_text(
        json.dumps(private_audit, indent=2)
    )

    print("\nE2 VIEWPOINT CHECK FINISHED", flush=True)

finally:
    if controller is not None:
        controller.stop()
