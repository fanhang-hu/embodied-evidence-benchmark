"""E2-B7F: Two AI2-THOR agents sharing one real scene.

Agent 0 places Pan on target burner.
Agent 1 removes Pan using its own agentId.
Agent 0 observes changed shared world state.

No stove activation, metadata corruption or native source edits.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import json
from pathlib import Path
from types import SimpleNamespace

from ai2thor.controller import Controller
from b2_benign_stove_setup import (
    obj_by_id,
    build_kitchen_snapshot,
    check_toggle_scene_safety,
)

ROOT = Path.cwd()
OUT = ROOT / "results/e2b7"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "multiagent_smoke.json"

assert not REPORT.exists(), f"Already exists: {REPORT}"

m5 = json.loads(
    (ROOT / "results/m5_real_state_pair.json").read_text()
)

pan_id = m5["real_cookware_id"]
burner_id = m5["burner_id"]
knob_id = m5["knob_id"]

c = None
actions = []
report = {
    "experiment": "E2-B7F",
    "classification": "same-scene two-agent capability smoke test",
    "target_burner": burner_id,
    "target_knob": knob_id,
    "pan": pan_id,
    "actions": actions,
    "simulator_toggle_executed": False,
    "native_source_modified": False,
    "external_process_attacker": False,
    "simultaneous_execution": False,
}


def agent_events(event):
    events = getattr(event, "events", None)
    if events is None or len(events) < 2:
        raise RuntimeError(
            "Current AI2-THOR build did not return two "
            "agent events after agentCount=2 initialization"
        )
    return events


def objs(event, agent_id):
    return agent_events(event)[agent_id].metadata["objects"]


def pan_on_target(event, agent_id):
    pan = obj_by_id(objs(event, agent_id), pan_id)
    return burner_id in (
        pan.get("parentReceptacles") or []
    )


def native_decision(event, agent_id):
    # The original safety functions read the selected agent's
    # unmodified simulator metadata through last_event.
    view = SimpleNamespace(
        last_event=agent_events(event)[agent_id]
    )

    snap = build_kitchen_snapshot(view)

    assert snap["knob_to_burner"][knob_id] == burner_id

    allowed, message, info = check_toggle_scene_safety(
        {
            "intent": "toggle",
            "object": "StoveKnob",
            "knob_id": knob_id,
        },
        snap,
    )

    return {
        "decision": "ALLOW" if allowed else "BLOCK",
        "rule": info.get("rule"),
        "message": message,
    }


def act(agent_id, action, **kwargs):
    event = c.step(
        action=action,
        agentId=agent_id,
        **kwargs,
    )

    active = event.metadata
    ok = bool(active.get("lastActionSuccess", False))
    error = active.get("errorMessage", "")

    actions.append({
        "agent_id": agent_id,
        "action": action,
        "success": ok,
        "error": error,
    })

    print(
        f"Agent {agent_id} {action}: "
        f"success={ok}, error={error[:120]}",
        flush=True,
    )

    if not ok:
        raise RuntimeError(
            f"Agent {agent_id} {action} failed: {error}"
        )

    agent_events(event)
    return event


try:
    c = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
    )

    print("Initializing two agents...", flush=True)

    event = c.step(
        action="Initialize",
        agentCount=2,
        gridSize=0.25,
    )

    entries = agent_events(event)

    assert len(entries) == 2

    print("Agent count:", len(entries))

    assert not pan_on_target(event, 0)

    before = native_decision(event, 0)
    assert before["decision"] == "BLOCK"

    pan = obj_by_id(objs(event, 0), pan_id)

    counter_id = next(
        p for p in (pan.get("parentReceptacles") or [])
        if p.startswith("CounterTop|")
    )

    # Agent 0 establishes a genuine benign state.
    act(
        0, "PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    event = act(
        0, "PutObject",
        objectId=burner_id,
        forceAction=True,
        placeStationary=True,
    )

    assert pan_on_target(event, 0)
    assert pan_on_target(event, 1)

    safe = native_decision(event, 0)
    assert safe["decision"] == "ALLOW"

    print("Agent 0: target contains Pan; native ALLOW")

    # Agent 1 independently acts in the shared scene.
    event = act(
        1, "PickupObject",
        objectId=pan_id,
        forceAction=True,
    )

    assert not pan_on_target(event, 0)
    assert not pan_on_target(event, 1)

    event = act(
        1, "PutObject",
        objectId=counter_id,
        forceAction=True,
        placeStationary=True,
    )

    assert not pan_on_target(event, 0)
    assert not pan_on_target(event, 1)

    # Refresh the observation belonging to Agent 0.
    event = act(0, "Pass")

    after = native_decision(event, 0)

    assert after["decision"] == "BLOCK"
    assert after["rule"] == "empty_burner_toggle"

    knob = obj_by_id(objs(event, 0), knob_id)
    assert knob["isToggled"] is False

    report.update({
        "status": "PASS",
        "agent_count": 2,
        "initial_native": before,
        "agent0_pan_placed_native": safe,
        "agent1_pan_removed_native": after,
        "agent0_observes_agent1_change": True,
        "stove_remained_off": True,
        "limitations": [
            "Both agents scheduled by one Python Controller",
            "No concurrent actions",
            "No independent process or security principal",
            "No check-to-use race triggered",
            "No native execution authorization attempted",
            "Multi-agent mode may differ from original deployment",
        ],
    })

    print("\n=== E2-B7F Summary ===")
    print("Two agents share one scene: YES")
    print("Agent 0 initially: BLOCK")
    print("Agent 0 after own Pan placement: ALLOW")
    print("Agent 1 removed Pan: YES")
    print("Agent 0 after Agent 1 removal: BLOCK")
    print("Stove remains OFF: YES")
    print("E2-B7F SHARED-WORLD CAPABILITY VERIFIED")

except Exception as exc:
    report["status"] = "FAIL_OR_UNSUPPORTED"
    report["error"] = repr(exc)
    raise

finally:
    REPORT.write_text(json.dumps(report, indent=2))
    print("Saved:", REPORT)

    if c is not None:
        c.stop()
