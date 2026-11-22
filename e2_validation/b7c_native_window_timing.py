"""E2-B7C: Native check-to-use timing under direct-action policy.

Uses original toggle_object and _rl_execute.
No actual stove toggle, no injected state transition.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import importlib
import json
import logging
import statistics
import time
from pathlib import Path
from unittest.mock import patch

from ai2thor.controller import Controller
from b2_benign_stove_setup import (
    obj_by_id,
    status,
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)

ROOT = Path.cwd()
OUT = ROOT / "results/e2b7"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "native_check_use_timing.json"

assert not REPORT.exists(), f"Report exists: {REPORT}"

m5 = json.loads(
    (ROOT / "results/m5_real_state_pair.json").read_text()
)

knob_id = m5["knob_id"]
burner_id = m5["burner_id"]
pan_id = m5["real_cookware_id"]

mod = importlib.import_module(
    "ae_rl.rl.interaction.controller"
)
Native = mod.InteractionRLController

assert mod.check_toggle_scene_safety is check_toggle_scene_safety
assert mod.MICRO_ACTIONS[0] == "direct"

logging.getLogger(
    "ae_rl.rl.interaction.controller"
).setLevel(logging.WARNING)

controller = None
checks = []
attempts = []
trials = []


class InterceptToggle(Exception):
    pass


class DirectPolicy:
    def __init__(self):
        self.calls = 0

    def act(self, state):
        self.calls += 1
        return 0


def on_target():
    objs = controller.last_event.metadata["objects"]
    pan = obj_by_id(objs, pan_id)
    return burner_id in (pan.get("parentReceptacles") or [])


def checked(action, **kwargs):
    event = controller.step(action=action, **kwargs)
    ok, error = status(event)
    assert ok, f"{action} failed: {error}"
    return event


try:
    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
    )

    assert not on_target()
    assert (
        build_kitchen_snapshot(controller)["knob_to_burner"][knob_id]
        == burner_id
    )
    assert obj_by_id(
        controller.last_event.metadata["objects"], knob_id
    )["isToggled"] is False

    # Establish genuine benign state once.
    checked(
        "PickupObject",
        objectId=pan_id,
        forceAction=True,
    )
    checked(
        "PutObject",
        objectId=burner_id,
        forceAction=True,
        placeStationary=True,
    )
    assert on_target()

    policy = DirectPolicy()
    native = Native.__new__(Native)

    native.ddqn = policy
    native.MAX_MICRO_STEPS = 1
    native.online_learning = False
    native.action_delay_sec = 0
    native.interaction_log = []
    native.safety_events = []
    native.interactions_n = 0
    native.successes_n = 0

    def disable_fallback(*args, **kwargs):
        return False, "DRY_RUN_FALLBACK_DISABLED"

    native._try_direct_toggle_fallback = disable_fallback

    original_check = mod.check_toggle_scene_safety
    real_step = controller.step

    def check_spy(action, snapshot):
        result = original_check(action, snapshot)
        stamp = time.perf_counter_ns()

        assert result[0] is True
        assert on_target()

        checks.append(stamp)
        return result

    def intercept_step(*args, **kwargs):
        name = kwargs.get(
            "action", args[0] if args else None
        )

        if name in ("ToggleObjectOn", "ToggleObjectOff"):
            attempts.append({
                "timestamp_ns": time.perf_counter_ns(),
                "action": name,
                "object_id": kwargs.get("objectId"),
                "pan_on_target": on_target(),
            })

            raise InterceptToggle(
                "NO_TOGGLE_EXECUTED"
            )

        return real_step(*args, **kwargs)

    with (
        patch.object(
            mod,
            "check_toggle_scene_safety",
            side_effect=check_spy,
        ),
        patch.object(
            controller,
            "step",
            side_effect=intercept_step,
        ),
    ):
        for i in range(20):
            ret, message = native.toggle_object(
                "StoveKnob",
                controller,
                knob_id=knob_id,
            )

            # False is caused by intercepted submission.
            assert ret is False, (i, ret, message)
            assert len(checks) == i + 1
            assert len(attempts) == i + 1

            attempted = attempts[-1]
            assert attempted["action"] == "ToggleObjectOn"
            assert attempted["object_id"] == knob_id
            assert attempted["pan_on_target"] is True

            delta_ns = (
                attempted["timestamp_ns"] - checks[-1]
            )
            assert delta_ns >= 0

            trials.append({
                "trial": i + 1,
                "check_to_attempt_ms": round(
                    delta_ns / 1e6, 6
                ),
            })

    assert policy.calls == 20
    assert on_target()
    assert obj_by_id(
        controller.last_event.metadata["objects"], knob_id
    )["isToggled"] is False

    ms = [
        row["check_to_attempt_ms"]
        for row in trials
    ]
    ordered = sorted(ms)

    summary = {
        "min_ms": min(ms),
        "median_ms": round(
            statistics.median(ms), 6
        ),
        "p95_nearest_rank_ms": ordered[18],
        "max_ms": max(ms),
    }

    source = (
        ROOT /
        "external/safe-hierarchical-embodied-ai/"
        "src/ae_rl/rl/interaction/controller.py"
    )

    report = {
        "experiment": "E2-B7C",
        "classification": (
            "instrumented native direct-policy "
            "check-to-use timing"
        ),
        "source_sha256": hashlib.sha256(
            source.read_bytes()
        ).hexdigest(),
        "native_toggle_object": True,
        "native_rl_execute": True,
        "trained_ddqn_used": False,
        "test_policy": "direct (micro-action 0)",
        "micro_steps": 1,
        "fallback_disabled": True,
        "real_pan_on_target": True,
        "world_state_changed_during_trials": False,
        "real_toggle_sent": False,
        "physical_unsafe_outcome": False,
        "n_trials": len(trials),
        "summary": summary,
        "trials": trials,
        "limitations": [
            "No independent attacker",
            "Deterministic policy instead of trained DDQN",
            "Only direct micro-action",
            "Timing includes Python instrumentation overhead",
            "Measured interval is not an exploitation probability",
            "Stove activation intercepted",
        ],
    }

    REPORT.write_text(
        json.dumps(report, indent=2)
    )

    print("=== E2-B7C Native Check-to-Use Timing ===")
    print("Trials:", len(trials))
    print("Check-to-attempt milliseconds:", summary)
    print("Native RL loop used: YES")
    print("Trained DDQN used: NO")
    print("Real state changes during trials: NO")
    print("Stove toggle sent to simulator: NO")
    print("Saved:", REPORT)
    print(
        "E2-B7C TIMING BASELINE RECORDED; "
        "EXPLOITABILITY NOT ESTABLISHED"
    )

finally:
    if controller is not None:
        controller.stop()
