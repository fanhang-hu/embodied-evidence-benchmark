import _bootstrap  # Workspace paths and historical cross-script imports.
from pathlib import Path
from ai2thor.controller import Controller

candidates = sorted(
    p for p in (
        Path.home() / ".ai2thor/releases"
    ).glob("thor-Linux64-f082*/thor-Linux64-f082*")
    if p.is_file()
)

if not candidates:
    raise FileNotFoundError(
        "Cached f082 Linux Player not found"
    )

build = candidates[0]
print("Player:", build, flush=True)

controller = None

try:
    controller = Controller(
        scene="FloorPlan1",
        local_executable_path=str(build),
        width=300,
        height=300,
        quality="Low",
    )

    objects = controller.last_event.metadata["objects"]
    print("Scene loaded:", len(objects), "objects")

    knobs = [
        o for o in objects
        if o.get("objectType") == "StoveKnob"
        and o.get("toggleable")
        and not o.get("isToggled")
    ]

    assert knobs, "No available StoveKnob"

    target = knobs[0]["objectId"]

    event = controller.step(
        action="ToggleObjectOn",
        objectId=target,
        forceAction=True,
    )

    success = event.metadata["lastActionSuccess"]

    after = next(
        o for o in event.metadata["objects"]
        if o["objectId"] == target
    )

    print("Action success:", success)
    print("Knob toggled:", after["isToggled"])

    assert success and after["isToggled"]

    print("P18 BASIC PLAYER COMPATIBILITY PASS")

finally:
    if controller is not None:
        controller.stop()
