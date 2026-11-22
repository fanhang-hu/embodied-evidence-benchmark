"""E2-B7E: Test a simple pre-execution revalidation gate.

Preserves original toggle_object, _rl_execute and kitchen-safety policy.
Uses a deterministic direct-action selector for CPU-only evaluation.

The test gate is added at the simulator submission boundary.
All StoveKnob toggle requests are intercepted, never executed.

No original source modifications and no external attacker.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import importlib
import json
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

REPORT = OUT / "preexecution_revalidation.json"
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
assert mod.MICRO_ACTIONS[0] == "direct"

c = None
cases = []
active = None


def objects():
    return c.last_event.metadata["objects"]


def on_target():
    pan = obj_by_id(objects(), pan_id)
    return burner_id in (
        pan.get("parentReceptacles") or []
    )


def checked(label, **kwargs):
    event = c.step(**kwargs)
    ok, error = status(event)

    assert ok, f"{label}: {error}"
    return event


def fresh_native_check():
    start = time.perf_counter_ns()

    verdict, message, info = original_check(
        {
            "intent": "toggle",
            "object": "StoveKnob",
            "knob_id": knob_id,
        },
        build_kitchen_snapshot(c),
    )

    elapsed_ms = (
        time.perf_counter_ns() - start
    ) / 1e6

    return {
        "decision": "ALLOW" if verdict else "BLOCK",
        "rule": info.get("rule"),
        "elapsed_ms": round(elapsed_ms, 6),
    }


def put_pan_on_target():
    assert not on_target()

    checked(
        "pickup_pan",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    checked(
        "put_pan_on_target",
        action="PutObject",
        objectId=burner_id,
        forceAction=True,
        placeStationary=True,
    )

    assert on_target()


def remove_pan_to_counter():
    assert on_target()

    checked(
        "remove_pan",
        action="PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    checked(
        "put_pan_on_counter",
        action="PutObject",
        objectId=counter_id,
        forceAction=True,
        placeStationary=True,
    )

    assert not on_target()


class DryRunSubmission(Exception):
    pass


class PreExecutionBlock(Exception):
    pass


class DirectTestPolicy:
    def __init__(self):
        self.calls = 0

    def act(self, state):
        self.calls += 1

        assert self.calls == 1
        assert active["initial_decision"] == "ALLOW"

        # This is an intentional in-process scheduling hook.
        # It is NOT an independently demonstrated attack.
        if active["remove_after_check"]:
            remove_pan_to_counter()
            active["world_changed_after_check"] = True

        return 0


def check_spy(request, snapshot):
    verdict = original_check(request, snapshot)

    if active is not None:
        active["initial_decision"] = (
            "ALLOW" if verdict[0] else "BLOCK"
        )
        active["check_time_ns"] = time.perf_counter_ns()
        active["pan_at_check"] = on_target()

    return verdict


def intercept_step(*args, **kwargs):
    name = kwargs.get(
        "action", args[0] if args else None
    )

    if name not in (
        "ToggleObjectOn",
        "ToggleObjectOff",
    ):
        return actual_step(*args, **kwargs)

    assert active is not None
    assert name == "ToggleObjectOn"
    assert kwargs.get("objectId") == knob_id

    active["reached_toggle_callback"] = True
    active["pan_at_submission"] = on_target()
    active["check_to_callback_ms"] = round(
        (
            time.perf_counter_ns()
            - active["check_time_ns"]
        ) / 1e6,
        6,
    )

    # Diagnostic check in both modes; only the guarded mode
    # enforces its result.
    current = fresh_native_check()
    active["fresh_decision_at_submission"] = (
        current["decision"]
    )
    active["fresh_rule"] = current["rule"]

    if active["use_guard"]:
        active["guard_check_ms"] = current["elapsed_ms"]

        if current["decision"] == "BLOCK":
            active["guard_blocked"] = True
            active["would_submit_after_guard"] = False
            raise PreExecutionBlock(
                "PRE_EXECUTION_REVALIDATION_BLOCK"
            )

    # No action is sent to the actual AI2-THOR simulator.
    active["would_submit_after_guard"] = True
    raise DryRunSubmission(
        "DRY_RUN_TOGGLE_NOT_EXECUTED"
    )


def run_case(name, *, initially_safe,
             remove_after_check, use_guard):
    global active

    if initially_safe:
        if not on_target():
            put_pan_on_target()
    else:
        assert not on_target()

    policy = DirectTestPolicy()

    native = Native.__new__(Native)
    native.ddqn = policy
    native.MAX_MICRO_STEPS = 1
    native.online_learning = False
    native.action_delay_sec = 0
    native.interaction_log = []
    native.safety_events = []
    native.interactions_n = 0
    native.successes_n = 0

    # Prevent any fallback from reaching an untested action path.
    native._try_direct_toggle_fallback = (
        lambda *args, **kwargs: (
            False,
            "DRY_RUN_FALLBACK_DISABLED",
        )
    )

    active = {
        "name": name,
        "initially_safe": initially_safe,
        "remove_after_check": remove_after_check,
        "use_guard": use_guard,
        "world_changed_after_check": False,
        "reached_toggle_callback": False,
        "guard_blocked": False,
        "would_submit_after_guard": False,
    }

    returned, message = native.toggle_object(
        "StoveKnob",
        c,
        knob_id=knob_id,
    )

    active["native_return_after_dryrun"] = returned
    active["native_message"] = message
    active["policy_calls"] = policy.calls
    active["final_pan_on_target"] = on_target()
    active["stove_still_off"] = (
        obj_by_id(objects(), knob_id)["isToggled"] is False
    )

    assert active["stove_still_off"]
    assert returned is False

    if not initially_safe:
        assert active["initial_decision"] == "BLOCK"
        assert not active["reached_toggle_callback"]
        assert policy.calls == 0
    else:
        assert active["initial_decision"] == "ALLOW"
        assert active["reached_toggle_callback"]
        assert policy.calls == 1

    if remove_after_check:
        assert active["world_changed_after_check"]
        assert active["fresh_decision_at_submission"] == "BLOCK"
        assert active["fresh_rule"] == "empty_burner_toggle"
    elif initially_safe:
        assert active["fresh_decision_at_submission"] == "ALLOW"

    cases.append(dict(active))

    print(
        f"{name}: "
        f"initial={active['initial_decision']}, "
        f"fresh={active.get('fresh_decision_at_submission', 'N/A')}, "
        f"guard_block={active['guard_blocked']}, "
        f"would_submit={active['would_submit_after_guard']}",
        flush=True,
    )

    active = None


try:
    c = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
    )

    pan = obj_by_id(objects(), pan_id)

    counter_id = next(
        p for p in (pan.get("parentReceptacles") or [])
        if p.startswith("CounterTop|")
    )

    assert not on_target()
    assert (
        build_kitchen_snapshot(c)["knob_to_burner"][knob_id]
        == burner_id
    )

    actual_step = c.step

    with (
        patch.object(
            mod,
            "check_toggle_scene_safety",
            side_effect=check_spy,
        ),
        patch.object(
            c,
            "step",
            side_effect=intercept_step,
        ),
    ):
        # 1. Unsafe at the original check: native BLOCK.
        run_case(
            "empty_native",
            initially_safe=False,
            remove_after_check=False,
            use_guard=False,
        )

        # 2. Legitimate operation: guard must preserve ALLOW.
        run_case(
            "benign_with_guard",
            initially_safe=True,
            remove_after_check=False,
            use_guard=True,
        )

        # Return Pan to countertop for next independent trial.
        remove_pan_to_counter()

        # 3. TOCTOU without guard: reaches submission.
        run_case(
            "toctou_no_guard",
            initially_safe=True,
            remove_after_check=True,
            use_guard=False,
        )

        # 4. Same controlled TOCTOU with revalidation.
        run_case(
            "toctou_with_guard",
            initially_safe=True,
            remove_after_check=True,
            use_guard=True,
        )

    by_name = {
        case["name"]: case
        for case in cases
    }

    assert not by_name["empty_native"][
        "reached_toggle_callback"
    ]

    assert by_name["benign_with_guard"][
        "would_submit_after_guard"
    ]

    assert by_name["toctou_no_guard"][
        "would_submit_after_guard"
    ]

    assert by_name["toctou_with_guard"][
        "guard_blocked"
    ]

    assert not by_name["toctou_with_guard"][
        "would_submit_after_guard"
    ]

    source = (
        ROOT /
        "external/safe-hierarchical-embodied-ai/"
        "src/ae_rl/rl/interaction/controller.py"
    )

    report = {
        "experiment": "E2-B7E",
        "classification": (
            "controlled native execution path "
            "with test-side revalidation gate"
        ),
        "native_controller_sha256": hashlib.sha256(
            source.read_bytes()
        ).hexdigest(),
        "original_toggle_object_used": True,
        "original_rl_execute_used": True,
        "original_safety_rule_used": True,
        "trained_ddqn_used": False,
        "test_action_policy": "direct",
        "guard_in_original_repository": False,
        "guard_location": "test-side submission interceptor",
        "independent_attacker_proven": False,
        "toggle_executed": False,
        "cases": cases,
        "limitations": [
            "Only one trial per condition",
            "In-process state-change scheduling",
            "Deterministic direct policy",
            "Guard implemented outside original repository",
            "No actual stove activation",
            "No independently exploitable race established",
            "Pre-submit check is not an atomic check-and-act",
        ],
    }

    REPORT.write_text(json.dumps(report, indent=2))

    print("\n=== E2-B7E Summary ===")
    print("Original empty-scene check: BLOCK")
    print("Legitimate operation preserved by guard: YES")
    print("TOCTOU without guard reaches submission: YES")
    print("TOCTOU with guard blocked before submission: YES")
    print("Actual stove activation: NO")
    print("Saved:", REPORT)
    print("E2-B7E CONTROLLED REVALIDATION TEST PASSED")

except Exception as exc:
    (OUT / "preexecution_revalidation_debug.json").write_text(
        json.dumps({
            "error": repr(exc),
            "completed_cases": cases,
            "active_case": active,
        }, indent=2)
    )
    raise

finally:
    if c is not None:
        c.stop()
