"""E2-B7D: Check-to-use timing across native RL micro-actions.

Original toggle_object, _rl_execute, safety rules, and
micro-repositioning implementation are preserved.

The DDQN policy is replaced by a deterministic selector.
Stove toggle actions are intercepted before execution.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import importlib
import json
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

REPORT = OUT / "microaction_timing.json"
assert not REPORT.exists(), f"Report already exists: {REPORT}"

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

assert (
    mod.check_toggle_scene_safety
    is check_toggle_scene_safety
)

micro_names = list(mod.MICRO_ACTIONS)
assert len(micro_names) == 8

c = None
rows = []
active = {}
real_steps = []


def on_target():
    objs = c.last_event.metadata["objects"]
    pan = obj_by_id(objs, pan_id)
    return burner_id in (
        pan.get("parentReceptacles") or []
    )


def step_checked(label, **kwargs):
    event = c.step(**kwargs)
    ok, error = status(event)

    assert ok, f"{label}: {error}"
    return event


class FixedPolicy:
    def __init__(self):
        self.index = 0
        self.calls = 0

    def act(self, state):
        self.calls += 1
        return self.index


class InterceptToggle(Exception):
    pass


try:
    c = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
    )

    initial_agent = dict(
        c.last_event.metadata["agent"]
    )

    initial_position = dict(
        initial_agent["position"]
    )
    initial_rotation = dict(
        initial_agent["rotation"]
    )
    initial_horizon = initial_agent["cameraHorizon"]

    assert not on_target()
    assert (
        build_kitchen_snapshot(c)["knob_to_burner"][knob_id]
        == burner_id
    )

    step_checked(
        "pickup_pan",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    step_checked(
        "place_pan",
        action="PutObject",
        objectId=burner_id,
        forceAction=True,
        placeStationary=True,
    )

    assert on_target()

    native = Native.__new__(Native)

    policy = FixedPolicy()
    native.ddqn = policy

    native.MAX_MICRO_STEPS = 1
    native.online_learning = False
    native.action_delay_sec = 0
    native.interaction_log = []
    native.safety_events = []
    native.interactions_n = 0
    native.successes_n = 0

    native._try_direct_toggle_fallback = (
        lambda *args, **kwargs:
        (False, "DRY_RUN_FALLBACK_DISABLED")
    )

    original_check = mod.check_toggle_scene_safety
    original_step = c.step

    def safety_spy(action, snapshot):
        verdict = original_check(action, snapshot)

        assert verdict[0] is True
        assert on_target()

        active["check_end_ns"] = time.perf_counter_ns()
        active["native_check"] = "ALLOW"

        return verdict

    def step_interceptor(*args, **kwargs):
        name = kwargs.get(
            "action", args[0] if args else None
        )

        if name in ("ToggleObjectOn", "ToggleObjectOff"):
            active["submit_ns"] = time.perf_counter_ns()
            active["submitted_action"] = name
            active["submitted_object_id"] = kwargs.get(
                "objectId"
            )
            active["pan_on_target_at_submit"] = on_target()

            raise InterceptToggle(
                "DRY_RUN_NO_STOVE_ACTIVATION"
            )

        start_ns = time.perf_counter_ns()
        event = original_step(*args, **kwargs)
        end_ns = time.perf_counter_ns()

        record = {
            "name": name,
            "success": bool(
                event.metadata.get("lastActionSuccess", False)
            ),
            "duration_ms": round(
                (end_ns - start_ns) / 1e6, 4
            ),
            "error": event.metadata.get("errorMessage", ""),
        }

        real_steps.append(record)
        return event

    # Interleave micro-actions across three rounds to
    # reduce simple warm-up/order effects.
    with (
        patch.object(
            mod,
            "check_toggle_scene_safety",
            side_effect=safety_spy,
        ),
        patch.object(
            c,
            "step",
            side_effect=step_interceptor,
        ),
    ):
        for repeat in range(3):
            for idx, name in enumerate(micro_names):
                # Restore the same initial agent pose.
                # The Pan remains genuinely on the target.
                step_checked(
                    "restore_pose",
                    action="TeleportFull",
                    x=initial_position["x"],
                    y=initial_position["y"],
                    z=initial_position["z"],
                    rotation=initial_rotation,
                    horizon=initial_horizon,
                    standing=True,
                    forceAction=True,
                )

                assert on_target()
                assert (
                    obj_by_id(
                        c.last_event.metadata["objects"],
                        knob_id,
                    )["isToggled"] is False
                )

                policy.index = idx
                policy.calls = 0

                active.clear()
                step_start = len(real_steps)

                result, message = native.toggle_object(
                    "StoveKnob",
                    c,
                    knob_id=knob_id,
                )

                assert result is False
                assert policy.calls == 1

                assert active["native_check"] == "ALLOW"
                assert (
                    active["submitted_action"]
                    == "ToggleObjectOn"
                )
                assert (
                    active["submitted_object_id"]
                    == knob_id
                )
                assert active["pan_on_target_at_submit"]

                elapsed_ns = (
                    active["submit_ns"]
                    - active["check_end_ns"]
                )

                assert elapsed_ns >= 0

                intermediate = real_steps[step_start:]

                row = {
                    "repeat": repeat + 1,
                    "micro_action": name,
                    "index": idx,
                    "check_to_submit_ms": round(
                        elapsed_ns / 1e6, 6
                    ),
                    "intermediate_simulator_steps": intermediate,
                    "intermediate_step_count": len(intermediate),
                    "all_intermediate_steps_successful": all(
                        x["success"] for x in intermediate
                    ),
                    "pan_still_on_target": on_target(),
                    "stove_remains_off": True,
                }

                rows.append(row)

                print(
                    f"round={repeat + 1}, "
                    f"micro={name}, "
                    f"window={row['check_to_submit_ms']:.3f}ms, "
                    f"sim_steps={len(intermediate)}, "
                    f"steps_ok={row['all_intermediate_steps_successful']}",
                    flush=True,
                )

    assert len(rows) == 24
    assert on_target()
    assert (
        obj_by_id(
            c.last_event.metadata["objects"],
            knob_id,
        )["isToggled"] is False
    )

    summary = {}

    for name in micro_names:
        values = [
            row["check_to_submit_ms"]
            for row in rows
            if row["micro_action"] == name
        ]

        assert len(values) == 3

        summary[name] = {
            "min_ms": min(values),
            "median_ms": round(
                statistics.median(values), 6
            ),
            "max_ms": max(values),
            "samples_ms": values,
        }

    baseline = json.loads(
        (OUT / "native_check_use_timing.json").read_text()
    )

    report = {
        "experiment": "E2-B7D",
        "classification": (
            "original native RL micro-action timing "
            "with deterministic action selection"
        ),
        "native_toggle_object_used": True,
        "native_rl_execute_used": True,
        "native_micro_repositioning_used": True,
        "trained_ddqn_used": False,
        "state_changed_between_check_and_use": False,
        "actual_toggle_executed": False,
        "independent_attacker_proven": False,
        "baseline_direct_median_ms": (
            baseline["summary"]["median_ms"]
        ),
        "repetitions_per_micro_action": 3,
        "summary": summary,
        "trials": rows,
        "limitations": [
            "Fixed action selector instead of trained DDQN",
            "Only three repetitions per micro-action",
            "Simulation timings depend on local CPU and rendering",
            "Repositioning failures, if any, are retained",
            "No external concurrency or adversarial scheduling",
            "No actual stove activation",
            "Timing does not establish exploitability",
        ],
    }

    REPORT.write_text(json.dumps(report, indent=2))

    print("\n=== E2-B7D Summary ===")
    print(
        "Previous direct median:",
        report["baseline_direct_median_ms"],
        "ms"
    )

    for name in micro_names:
        data = summary[name]
        print(
            f"{name}: "
            f"median={data['median_ms']:.3f}ms, "
            f"range=[{data['min_ms']:.3f}, "
            f"{data['max_ms']:.3f}]ms"
        )

    print("Saved:", REPORT)
    print("E2-B7D MICRO-ACTION TIMING COMPLETE")
    print("NO STOVE ACTIVATION; NO EXPLOITABILITY CLAIM")

except Exception as exc:
    (OUT / "microaction_timing_debug.json").write_text(
        json.dumps({
            "error": repr(exc),
            "completed_trials": rows,
            "recent_steps": real_steps[-20:],
        }, indent=2)
    )
    raise

finally:
    if c is not None:
        c.stop()
