import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
import time
from pathlib import Path

from ai2thor.controller import Controller

ROOT = _bootstrap.ROOT
REPO = ROOT / "external" / "SafeAgentBench"
sys.path.insert(0, str(REPO))

from low_level_controller.low_level_controller import LowLevelPlanner
from evaluator.detail_evaluate import compute_SR_object_state


def get_object(event, object_id):
    for obj in event.metadata["objects"]:
        if obj["objectId"] == object_id:
            return obj
    raise RuntimeError(f"Object not found: {object_id}")


with (REPO / "dataset/safe_detailed_1009.jsonl").open() as f:
    dataset = [json.loads(line) for line in f if line.strip()]

task = dataset[4]

assert task["scene_name"] == "FloorPlan1"
assert task["final_state"] is not None

print("=== Official Dataset Task ===", flush=True)
print("Instruction:", task["instruction"])
print("Scene:", task["scene_name"])
print("Steps:", task["step"])
print("Target state:", task["final_state"])

controller = None
pot_id = None

try:
    controller = Controller(
        scene=task["scene_name"],
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    planner = LowLevelPlanner(controller)
    planner.restore_scene()

    print("\n=== Execute Official Actions ===", flush=True)

    for i, action in enumerate(task["step"], 1):
        start = time.perf_counter()

        result = planner.llm_skill_interact(action)

        elapsed = time.perf_counter() - start

        print(f"\nStep {i}: {action}", flush=True)
        print("Result:", result, flush=True)
        print("Time:", round(elapsed, 3), "s", flush=True)

        if not result["success"]:
            raise RuntimeError(f"Step {i} failed: {result}")

        if action == "pick pot":
            inventory = controller.last_event.metadata["inventoryObjects"]
            assert len(inventory) == 1, "Pot was not picked up"
            pot_id = inventory[0]["objectId"]
            print("Picked object ID:", pot_id, flush=True)

    print("\n=== Official State Evaluator ===", flush=True)

    objects = controller.last_event.metadata["objects"]

    sr, avg_sr = compute_SR_object_state(
        objects,
        task["final_state"]
    )

    print("Official state SR:", sr)
    print("Official average state score:", avg_sr)

    print("\n=== Exact Object Verification ===", flush=True)

    assert pot_id is not None
    pot = get_object(controller.last_event, pot_id)

    parents = pot.get("parentReceptacles") or []

    placed_correctly = any(
        parent.split("|")[0] == "CounterTop"
        for parent in parents
    )

    print("Pot ID:", pot_id)
    print("Parent receptacles:", parents)
    print("Exact target placed correctly:", placed_correctly)

    assert sr == 1.0, "Official evaluator failed"
    assert placed_correctly, "Tracked Pot not on CounterTop"

    print("\nALL TESTS PASSED", flush=True)

finally:
    if controller is not None:
        controller.stop()
