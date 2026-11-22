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

OUT = ROOT / "results" / "e2_observations"
OUT.mkdir(parents=True, exist_ok=True)

with (REPO / "dataset/unsafe_detailed_1009.jsonl").open() as f:
    tasks = [json.loads(line) for line in f if line.strip()]

task = tasks[11]
assert task["scene_name"] == "FloorPlan1"

controller = None
observations = []
private_audit = []


def get_object(name):
    matches = [
        o for o in controller.last_event.metadata["objects"]
        if o["objectType"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def capture(name, elapsed_s=None):
    event = controller.last_event
    card = get_object("CreditCard")
    microwave = get_object("Microwave")

    parents = card.get("parentReceptacles") or []
    children = microwave.get("receptacleObjectIds") or []

    inside = (
        microwave["objectId"] in parents
        or card["objectId"] in children
    )

    assert event.frame is not None
    assert event.depth_frame is not None
    assert np.isfinite(event.depth_frame).all()

    rgb_path = OUT / f"{name}.png"
    depth_path = OUT / f"{name}_depth.npy"

    Image.fromarray(event.frame).save(rgb_path)
    np.save(depth_path, event.depth_frame)

    # 可供未来视觉核验器使用的观察清单：
    # 不包含模拟器真实对象属性。
    observations.append({
        "frame_id": name,
        "rgb_file": rgb_path.name,
        "depth_file": depth_path.name,
        "capture_time_ns": time.time_ns(),
        "refresh_latency_s": elapsed_s,
    })

    # 仅供研究者离线标注和评价。
    private_audit.append({
        "frame_id": name,
        "card_inside": inside,
        "card_visible_metadata": card["visible"],
        "microwave_visible_metadata": microwave["visible"],
        "microwave_isOpen": microwave["isOpen"],
        "microwave_isToggled": microwave["isToggled"],
    })

    print(
        f"{name}: "
        f"card_inside={inside}, "
        f"card_visible={card['visible']}, "
        f"door_open={microwave['isOpen']}, "
        f"rgb={rgb_path}",
        flush=True
    )

    return inside, microwave["isOpen"]


try:
    print("=== E2 Observation Audit ===", flush=True)

    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True,
    )

    planner = LowLevelPlanner(controller)
    planner.restore_scene()

    for instruction in task["step"][:6]:
        result = planner.llm_skill_interact(instruction)

        print(instruction, result["success"], flush=True)
        assert result["success"], result

        if instruction == "put Microwave":
            inside, door_open = capture("after_put")
            assert inside and door_open

        if instruction == "close Microwave":
            inside, door_open = capture("after_close")
            assert inside and not door_open

    # 获取新的 RGB/Depth，但不改变微波炉开关状态。
    start = time.perf_counter()
    event = controller.step(action="Pass")
    refresh_s = time.perf_counter() - start

    assert event.metadata["lastActionSuccess"]
    inside, door_open = capture(
        "fresh_after_pass",
        elapsed_s=round(refresh_s, 4)
    )

    assert inside and not door_open
    assert get_object("Microwave")["isToggled"] is False

    (OUT / "observation_manifest.json").write_text(
        json.dumps(observations, indent=2)
    )

    (OUT / "private_ground_truth.json").write_text(
        json.dumps(private_audit, indent=2)
    )

    print("\nFresh observation latency:", round(refresh_s, 3), "s")
    print("E2 OBSERVATION CAPTURE PASSED", flush=True)

finally:
    if controller is not None:
        controller.stop()
