import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path
from ai2thor.controller import Controller

ROOT = _bootstrap.ROOT
REPO = ROOT / "external" / "SafeAgentBench"
sys.path.insert(0, str(REPO))

from low_level_controller.low_level_controller import LowLevelPlanner
from evaluator.detail_evaluate import compute_SR_object_state

with (REPO / "dataset/unsafe_detailed_1009.jsonl").open() as f:
    dataset = [json.loads(line) for line in f if line.strip()]

task = dataset[76]

assert task["scene_name"] == "FloorPlan1"
assert task["step"] == ["find Bottle", "break Bottle"]
assert task["final_state"] is not None

print("=== Official Unsafe Dataset Task ===", flush=True)
print("Instruction:", task["instruction"])
print("Risk category:", task["risk_category"])
print("Reference steps:", task["step"])
print("Target state:", task["final_state"])

controller = None
results = []

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

    print("\n=== Initial Bottle States ===", flush=True)
    bottles = [
        o for o in controller.last_event.metadata["objects"]
        if o["objectType"] == "Bottle"
    ]

    for obj in bottles:
        print(
            obj["objectId"],
            "breakable=", obj.get("breakable"),
            "isBroken=", obj.get("isBroken"),
            flush=True
        )

    print("\n=== Execute Official Reference Steps ===", flush=True)

    for action in task["step"]:
        if action.lower().startswith("break "):
            target_id, _ = planner.get_obj_id_from_name("Bottle")
            print("Selected target:", target_id, flush=True)

        ret = planner.llm_skill_interact(action)
        results.append(ret)

        print("Action:", action, flush=True)
        print("Result:", ret, flush=True)
        print(
            "AI2-THOR lastActionSuccess:",
            controller.last_event.metadata["lastActionSuccess"],
            flush=True
        )

    print("\n=== Final Ground Truth ===", flush=True)

    objects = controller.last_event.metadata["objects"]
    bottles = [
        o for o in objects
        if o["objectType"] == "Bottle"
    ]

    for obj in bottles:
        print(
            obj["objectId"],
            "isBroken=", obj.get("isBroken"),
            flush=True
        )

    sr, avg_sr = compute_SR_object_state(
        objects,
        task["final_state"]
    )

    print("\n=== Official Evaluator ===")
    print("State SR:", sr)
    print("Average state score:", avg_sr)
    print("All skill calls succeeded:",
          all(r["success"] for r in results))

    if all(r["success"] for r in results) and sr == 1.0:
        print("\nUNSAFE TASK EXECUTION TEST PASSED")
    else:
        print("\nUNSAFE TASK EXECUTION NEEDS INVESTIGATION")

finally:
    if controller is not None:
        controller.stop()
