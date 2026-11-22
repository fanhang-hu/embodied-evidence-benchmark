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

with (REPO / "dataset/safe_detailed_1009.jsonl").open() as f:
    dataset = [json.loads(line) for line in f if line.strip()]

task = dataset[4]
assert task["scene_name"] == "FloorPlan1"

Path("results").mkdir(exist_ok=True)

controller = None
records = []

try:
    print("=== M0-C Repeated Interaction Test ===", flush=True)

    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    for episode in range(1, 11):
        print(f"\n=== Episode {episode}/10 ===", flush=True)

        record = {
            "episode": episode,
            "actions": [],
            "passed": False
        }
        records.append(record)

        try:
            start = time.perf_counter()
            event = controller.reset(scene="FloorPlan1")
            record["reset_s"] = round(
                time.perf_counter() - start, 3
            )

            if not event.metadata["lastActionSuccess"]:
                raise RuntimeError("Scene reset failed")

            planner = LowLevelPlanner(controller)
            planner.restore_scene()

            pot_id = None

            for action in task["step"]:
                start = time.perf_counter()
                result = planner.llm_skill_interact(action)
                elapsed = time.perf_counter() - start

                record["actions"].append({
                    "action": action,
                    "time_s": round(elapsed, 3),
                    "result": result
                })

                print(
                    action,
                    result["success"],
                    f"{elapsed:.3f}s",
                    flush=True
                )

                if not result["success"]:
                    raise RuntimeError(
                        f"{action}: {result['message']}"
                    )

                if action == "pick pot":
                    inventory = controller.last_event.metadata[
                        "inventoryObjects"
                    ]
                    if len(inventory) != 1:
                        raise RuntimeError("Pickup verification failed")
                    pot_id = inventory[0]["objectId"]

            objects = controller.last_event.metadata["objects"]

            sr, avg_sr = compute_SR_object_state(
                objects,
                task["final_state"]
            )

            record["official_sr"] = sr
            record["official_avg_sr"] = avg_sr

            pot = next(
                obj for obj in objects
                if obj["objectId"] == pot_id
            )

            parents = pot.get("parentReceptacles") or []

            exact_success = any(
                p.split("|")[0] == "CounterTop"
                for p in parents
            )

            record["pot_id"] = pot_id
            record["parent_receptacles"] = parents
            record["exact_success"] = exact_success

            if sr != 1.0 or not exact_success:
                raise RuntimeError(
                    "Official or exact-state verification failed"
                )

            record["passed"] = True
            print("EPISODE PASSED", flush=True)

        except Exception as e:
            record["error"] = repr(e)
            print("EPISODE FAILED:", repr(e), flush=True)

    passed = sum(r["passed"] for r in records)

    print("\n=== Final Summary ===", flush=True)
    print(f"Passed episodes: {passed}/10", flush=True)
    print(f"Failed episodes: {10 - passed}/10", flush=True)

    if passed == 10:
        print("INTERACTION STABILITY TEST PASSED", flush=True)
    else:
        print("INTERACTION STABILITY NEEDS INVESTIGATION", flush=True)

finally:
    if controller is not None:
        controller.stop()

    with open("results/m0c_interaction.json", "w") as f:
        json.dump(records, f, indent=2)
