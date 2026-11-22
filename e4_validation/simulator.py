"""Small explicit AI2-THOR setup helpers. Setup and evaluated actions stay separate."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/SafeAgentBench"))
sys.path.insert(0, str(ROOT / "external/safe-hierarchical-embodied-ai/src"))


def objects(controller):
    return copy.deepcopy(controller.last_event.metadata["objects"])


def by_id(items, object_id):
    return next(o for o in items if o["objectId"] == object_id)


def receipt(event, request):
    return {"request": request, "success": bool(event.metadata["lastActionSuccess"]),
            "error": event.metadata.get("errorMessage", ""),
            "last_action": event.metadata.get("lastAction")}


def step(controller, request, log):
    event = controller.step(**request)
    result = receipt(event, request)
    log.append(result)
    return result


def start_controller(scene):
    import tempfile
    from ai2thor.controller import Controller
    # Controller.log_dir is a read-only property, not a constructor setting.
    # Redirect only logs; keep the installed environment and Unity binary untouched.
    class WorkspaceLogController(Controller):
        @property
        def log_dir(self):
            return self.e4_log_dir
    log_dir = tempfile.mkdtemp(prefix="e4-unity-log-")
    WorkspaceLogController.e4_log_dir = log_dir
    release = Path.home() / ".ai2thor/releases/thor-Linux64-f0825767cd50d69f666c7f282e54abfe58f1e917"
    executable = release / "thor-Linux64-f0825767cd50d69f666c7f282e54abfe58f1e917"
    return WorkspaceLogController(scene=scene, width=640, height=480, quality="Low", headless=True, x_display="0",
                      renderDepthImage=False, local_executable_path=str(executable),
                      server_start_timeout=60, visibilityDistance=1.5)


def approach(controller, object_id, log):
    """Exact target binding, native reachable positions and unforced TeleportFull.

    Used only for navigation/setup, never changes object state or authorizes actions.
    Multiple poses are tested because visibility and hand clearance are independent.
    """
    target = by_id(objects(controller), object_id)
    event = controller.step(action="GetReachablePositions")
    positions = event.metadata.get("actionReturn") or []
    p = target["position"]
    positions.sort(key=lambda q: (q["x"]-p["x"])**2 + (q["z"]-p["z"])**2)
    for q in positions[:15]:
        dx, dz = p["x"]-q["x"], p["z"]-q["z"]
        rotation = math.degrees(math.atan2(dx, dz)) % 360
        camera_y = q["y"] + .675
        horizon = max(-30, min(60, -math.degrees(math.atan2(p["y"]-camera_y, math.hypot(dx, dz)))))
        req = dict(action="TeleportFull", **q, rotation=rotation, horizon=horizon, standing=True)
        result = step(controller, req, log)
        now = by_id(objects(controller), object_id)
        if result["success"] and now.get("visible"):
            return True
    return False


def prepare(controller, scene, pan_id, burner_id, knob_id, occupied, active):
    """Privileged evaluator setup; forceAction permitted ONLY here and logged.

    No metadata mutation. Final candidate actions always forceAction=False.
    """
    log = []
    controller.reset(scene=scene)
    initial = objects(controller)
    pan = by_id(initial, pan_id)
    assert pan["objectType"] in ("Pan", "Pot")
    assert all(not o.get("isToggled") for o in initial if o["objectType"] == "StoveKnob")
    if occupied:
        for req in [dict(action="PickupObject", objectId=pan_id, forceAction=True),
                    dict(action="PutObject", objectId=burner_id, forceAction=True, placeStationary=True)]:
            assert step(controller, req, log)["success"], log[-1]
        assert burner_id in (by_id(objects(controller), pan_id).get("parentReceptacles") or [])
    else:
        assert burner_id not in (pan.get("parentReceptacles") or [])
        assert not by_id(initial, burner_id).get("receptacleObjectIds")
    if active:
        assert approach(controller, knob_id, log), "Cannot approach knob for setup"
        assert step(controller, dict(action="ToggleObjectOn", objectId=knob_id, forceAction=False), log)["success"], log[-1]
    target = pan_id if occupied else knob_id
    assert approach(controller, target, log), f"Cannot approach {target}"
    return log
