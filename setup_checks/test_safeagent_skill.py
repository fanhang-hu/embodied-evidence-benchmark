import _bootstrap  # Workspace paths and historical cross-script imports.
from ai2thor.controller import Controller
from low_level_controller.low_level_controller import LowLevelPlanner
from PIL import Image
import time


def get_microwave(event):
    objects = [
        o for o in event.metadata["objects"]
        if o["objectType"] == "Microwave"
    ]
    assert len(objects) == 1, (
        f"Expected 1 microwave, found {len(objects)}"
    )
    return objects[0]


controller = None

try:
    print("=== 1. Initialize AI2-THOR ===", flush=True)

    start = time.perf_counter()

    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    planner = LowLevelPlanner(controller)
    planner.restore_scene()

    print("Initialization:", round(time.perf_counter()-start, 3), "s")

    microwave = get_microwave(controller.last_event)
    initial_open = microwave["isOpen"]

    print("Object ID:", microwave["objectId"])
    print("Initial isOpen:", initial_open)

    assert initial_open is False

    print("\n=== 2. Official High-Level Find ===", flush=True)

    start = time.perf_counter()
    result = planner.llm_skill_interact("find microwave")

    print("Find result:", result)
    print("Find time:", round(time.perf_counter()-start, 3), "s")

    assert result["success"], result

    microwave = get_microwave(controller.last_event)

    print("Visible:", microwave["visible"])
    print("Distance:", microwave["distance"])

    Image.fromarray(controller.last_event.frame).save(
        "safeagent_before.png"
    )

    print("\n=== 3. Official High-Level Open ===", flush=True)

    start = time.perf_counter()
    result = planner.llm_skill_interact("open microwave")

    print("Open result:", result)
    print("Open time:", round(time.perf_counter()-start, 3), "s")

    microwave = get_microwave(controller.last_event)

    print("After isOpen:", microwave["isOpen"])

    Image.fromarray(controller.last_event.frame).save(
        "safeagent_after.png"
    )

    assert result["success"], result
    assert microwave["isOpen"] is True

    print("\n=== 4. Reset Test ===", flush=True)

    controller.reset(scene="FloorPlan1")

    microwave = get_microwave(controller.last_event)

    print("After reset isOpen:", microwave["isOpen"])

    assert microwave["isOpen"] is False

    print("\nALL TESTS PASSED")

finally:
    if controller is not None:
        controller.stop()
