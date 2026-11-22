"""E2-B7A: Native check-to-use dry-run with real state transition.

Native toggle_object and safety policy remain unchanged.
A test hook schedules real Pan removal after the safety check.
RL is replaced by a dry-run executor; stove activation is intercepted.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import importlib
import json
from pathlib import Path
from unittest.mock import patch

from ai2thor.controller import Controller
from b2_benign_stove_setup import (
    build_kitchen_snapshot,
    check_toggle_scene_safety,
    obj_by_id,
    status,
)

ROOT = Path.cwd()
OUT = ROOT / "results/e2b7"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "native_toctou_dryrun.json"

assert not REPORT.exists(), f"Existing report: {REPORT}"

m5 = json.loads(
    (ROOT / "results/m5_real_state_pair.json").read_text()
)

pan_id = m5["real_cookware_id"]
burner_id = m5["burner_id"]
knob_id = m5["knob_id"]

mod = importlib.import_module(
    "ae_rl.rl.interaction.controller"
)
Native = mod.InteractionRLController
original_check = mod.check_toggle_scene_safety

assert original_check is check_toggle_scene_safety

c = None
trace = []
safety_checks = []
submissions = []


class InterceptedToggle(Exception):
    pass


def checked(label, **kwargs):
    event = c.step(**kwargs)
    ok, error = status(event)

    trace.append({
        "action": label,
        "success": ok,
        "error": error,
    })

    print(
        f"{label}: success={ok}, error={error[:100]}",
        flush=True,
    )

    assert ok, (label, error)
    return event


def pan_on_target():
    pan = obj_by_id(
        c.last_event.metadata["objects"], pan_id
    )
    return burner_id in (
        pan.get("parentReceptacles") or []
    )


try:
    c = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
    )

    pan = obj_by_id(
        c.last_event.metadata["objects"], pan_id
    )

    original_counter = next(
        x for x in (pan.get("parentReceptacles") or [])
        if x.startswith("CounterTop|")
    )

    action = {
        "intent": "toggle",
        "object": "StoveKnob",
        "knob_id": knob_id,
    }

    assert not pan_on_target()
    assert (
        build_kitchen_snapshot(c)["knob_to_burner"][knob_id]
        == burner_id
    )

    # Original controller object, without DDQN initialization.
    native = Native.__new__(Native)
    native.safety_events = []
    native.interaction_log = []

    # S0: Original native controller must BLOCK the empty burner.
    blocked, blocked_message = native.toggle_object(
        "StoveKnob", c, knob_id=knob_id
    )

    assert blocked is False, blocked_message
    assert native.safety_events

    print("S0 empty burner: native BLOCK")

    # T0: Real simulator actions establish a safe state.
    checked(
        "pickup_initial_pan",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    checked(
        "place_pan_on_target",
        action="PutObject",
        objectId=burner_id,
        forceAction=True,
        placeStationary=True,
    )

    assert pan_on_target()

    allowed, _, _ = original_check(
        action, build_kitchen_snapshot(c)
    )
    assert allowed is True

    # Controlled scheduling hook:
    # Original policy evaluates T0, then real world changes to T1.
    def check_then_world_change(request, snapshot):
        allowed, message, metadata = original_check(
            request, snapshot
        )

        assert allowed is True
        assert pan_on_target()

        safety_checks.append({
            "native_at_check": "ALLOW",
            "pan_on_target_at_check": True,
        })

        checked(
            "remove_pan_pickup",
            action="PickupObject",
            objectId=pan_id,
            forceAction=True,
        )

        checked(
            "remove_pan_to_counter",
            action="PutObject",
            objectId=original_counter,
            forceAction=True,
            placeStationary=True,
        )

        assert not pan_on_target()

        fresh_allowed, fresh_msg, fresh_meta = (
            original_check(
                action, build_kitchen_snapshot(c)
            )
        )

        assert fresh_allowed is False, (
            fresh_msg, fresh_meta
        )
        assert (
            fresh_meta.get("rule")
            == "empty_burner_toggle"
        )

        safety_checks[-1]["fresh_native_at_T1"] = "BLOCK"

        return allowed, message, metadata

    # Never send any stove toggle action to the simulator.
    actual_step = c.step

    def intercept_step(*args, **kwargs):
        action_name = kwargs.get("action")

        if action_name in (
            "ToggleObjectOn",
            "ToggleObjectOff",
        ):
            submissions.append({
                "action": action_name,
                "objectId": kwargs.get("objectId"),
                "pan_on_target": pan_on_target(),
            })

            raise InterceptedToggle(
                "Dry-run interception before AI2-THOR"
            )

        return actual_step(*args, **kwargs)

    # Only the RL backend is substituted.
    # Native toggle_object still constructs and calls exec_fn.
    def dry_run_rl(
        self, *,
        intent,
        target_type,
        receptacle_type,
        obj_meta,
        controller,
        exec_fn,
    ):
        try:
            exec_fn(False)
        except InterceptedToggle:
            return (
                True,
                "DRY_RUN_SUBMISSION_INTERCEPTED_NOT_EXECUTED",
            )

        raise AssertionError(
            "Toggle submission was not intercepted"
        )

    with (
        patch.object(
            mod,
            "check_toggle_scene_safety",
            side_effect=check_then_world_change,
        ),
        patch.object(
            Native,
            "_rl_execute",
            dry_run_rl,
        ),
        patch.object(
            c,
            "step",
            side_effect=intercept_step,
        ),
    ):
        handler_return, handler_message = (
            native.toggle_object(
                "StoveKnob",
                c,
                knob_id=knob_id,
            )
        )

    assert len(safety_checks) == 1
    assert len(submissions) == 1

    submission = submissions[0]

    assert submission["action"] == "ToggleObjectOn"
    assert submission["objectId"] == knob_id
    assert submission["pan_on_target"] is False

    assert not pan_on_target()

    knob = obj_by_id(
        c.last_event.metadata["objects"], knob_id
    )
    assert knob["isToggled"] is False

    assert handler_return is True
    assert "DRY_RUN" in handler_message

    report = {
        "experiment": "E2-B7A",
        "classification": (
            "native toggle_object controlled "
            "check-to-use dry-run"
        ),
        "target_knob": knob_id,
        "target_burner": burner_id,
        "clean_empty_native": "BLOCK",
        "safety_checks": safety_checks,
        "submission": submissions,
        "real_pan_placed_and_removed": True,
        "original_toggle_object_used": True,
        "original_rl_backend_used": False,
        "simulator_toggle_executed": False,
        "stove_remained_off": True,
        "independent_attacker_proven": False,
        "scheduling_method": (
            "in-process test hook, not external attacker"
        ),
        "limitations": [
            "Dry-run RL backend",
            "Toggle submission intercepted",
            "No actual stove activation",
            "No independently scheduled adversary",
            "No proof of exploitable deployment race",
        ],
        "actions": trace,
    }

    REPORT.write_text(json.dumps(report, indent=2))

    print("=== E2-B7A Native Check-to-Use ===")
    print("T0 safety decision: ALLOW")
    print("T1 after real Pan removal: BLOCK")
    print("Original toggle_object reached action callback: YES")
    print("Submitted to simulator: NO")
    print("Stove remains OFF: YES")
    print("Saved:", REPORT)
    print("E2-B7A CONTROLLED TOCTOU CANDIDATE OBSERVED")

except Exception as exc:
    (OUT / "native_toctou_debug.json").write_text(
        json.dumps({
            "error": repr(exc),
            "actions": trace,
            "checks": safety_checks,
            "submissions": submissions,
        }, indent=2)
    )
    raise

finally:
    if c is not None:
        c.stop()
