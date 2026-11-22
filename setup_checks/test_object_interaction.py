import _bootstrap  # Workspace paths and historical cross-script imports.
from ai2thor.controller import Controller
from PIL import Image
import math
import time

SCENE = "FloorPlan1"

def find_obj(event, object_id):
    for obj in event.metadata["objects"]:
        if obj["objectId"] == object_id:
            return obj
    raise RuntimeError(f"Object not found: {object_id}")

c = None
passed = False

try:
    start = time.perf_counter()

    c = Controller(
        scene=SCENE,
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    print("=== 1. Discover Objects ===", flush=True)

    objects = c.last_event.metadata["objects"]

    candidates = [
        o for o in objects
        if o.get("openable") or o.get("toggleable")
    ]

    priority = {
        "Microwave": 0,
        "Fridge": 1,
        "Faucet": 2,
        "Cabinet": 3,
        "Drawer": 4,
        "LightSwitch": 5,
        "StoveKnob": 6,
    }

    candidates.sort(
        key=lambda o: priority.get(o["objectType"], 99)
    )

    print("Total objects:", len(objects), flush=True)
    print("Interactive candidates:", len(candidates), flush=True)

    for o in candidates[:15]:
        print(
            o["objectType"],
            "openable=", o.get("openable"),
            "toggleable=", o.get("toggleable"),
            flush=True
        )

    print("\n=== 2. Find Reachable Positions ===", flush=True)

    e = c.step(action="GetReachablePositions")
    assert e.metadata["lastActionSuccess"], e.metadata["errorMessage"]

    reachable = e.metadata["actionReturn"]
    print("Reachable positions:", len(reachable), flush=True)

    print("\n=== 3. Test Interaction ===", flush=True)

    for target in candidates[:12]:
        object_id = target["objectId"]
        object_type = target["objectType"]

        pos = target["position"]

        nearby = [
            p for p in reachable
            if math.hypot(
                p["x"] - pos["x"],
                p["z"] - pos["z"]
            ) <= 2.0
        ]

        if not nearby:
            continue

        print(f"\nTrying {object_type}: {object_id}", flush=True)

        e = c.step(
            action="GetInteractablePoses",
            objectId=object_id,
            positions=nearby,
            rotations=list(range(0, 360, 45)),
            horizons=[-30, 0, 30, 60],
            standings=[True]
        )

        if not e.metadata["lastActionSuccess"]:
            print("Pose query failed:", e.metadata["errorMessage"])
            continue

        poses = e.metadata["actionReturn"] or []
        print("Available poses:", len(poses), flush=True)

        for pose in poses[:8]:
            e = c.step(action="TeleportFull", **pose)

            if not e.metadata["lastActionSuccess"]:
                continue

            obj = find_obj(e, object_id)

            if not obj.get("visible", False):
                continue

            if obj["openable"]:
                field = "isOpen"
                action = (
                    "CloseObject" if obj[field]
                    else "OpenObject"
                )
            else:
                field = "isToggled"
                action = (
                    "ToggleObjectOff" if obj[field]
                    else "ToggleObjectOn"
                )

            before = obj[field]

            Image.fromarray(e.frame).save(
                "interaction_before.png"
            )

            e = c.step(
                action=action,
                objectId=object_id,
                forceAction=False
            )

            after_obj = find_obj(e, object_id)
            after = after_obj[field]

            print("Action:", action, flush=True)
            print("Action success:", e.metadata["lastActionSuccess"])
            print("Before:", before)
            print("After:", after)

            if not e.metadata["lastActionSuccess"]:
                print("Reason:", e.metadata["errorMessage"])
                continue

            if before == after:
                print("State did not change")
                continue

            assert e.frame is not None
            assert e.depth_frame is not None

            Image.fromarray(e.frame).save(
                "interaction_after.png"
            )

            print("\n=== 4. Reset Test ===", flush=True)

            e = c.reset(scene=SCENE)
            reset_obj = find_obj(e, object_id)
            reset_state = reset_obj[field]

            print("After reset:", reset_state)

            assert reset_state == before, (
                "Reset did not restore object state"
            )

            print("\n=== RESULT ===")
            print("Object:", object_type)
            print("Object ID:", object_id)
            print("Field:", field)
            print("Before:", before)
            print("After:", after)
            print("Reset:", reset_state)
            print("Runtime:", round(time.perf_counter()-start, 2), "s")
            print("ALL TESTS PASSED")

            passed = True
            break

        if passed:
            break

    if not passed:
        raise RuntimeError(
            "No successful interaction found. "
            "Inspect candidate objects and action errors."
        )

finally:
    if c is not None:
        c.stop()
