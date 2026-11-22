#!/usr/bin/env python3
"""Generate E2-B safe positive control from the E2-A same-engine recheck.

Never edits E1, E2-A scripts or their JSON. Fails if code anchors drift.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.
from pathlib import Path
import ast

SRC = Path('e3_baseline/b7_percepttwin/e3_percepttwin_e2_fresh_recheck.py')
DST = Path('e3_baseline/b7_percepttwin/e3_percepttwin_e2b_positive_control.py')


def replace_once(text, old, new, name):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{name}: expected exactly one source anchor, got {count}; no destination written')
    return text.replace(old, new, 1)


if DST.exists():
    raise FileExistsError(f'Preserving existing E2-B script: {DST}')

source = SRC.read_text(encoding='utf-8')
s = source
s = replace_once(
    s,
    'assert CASE in ("clean", "corrupted", "oracle", "corrupted_freshcheck")',
    'assert CASE in ("clean", "corrupted", "oracle", "corrupted_freshcheck", "clean_positive")',
    'add positive case',
)
s = replace_once(
    s,
    '"experiment": "E2_same_engine_trusted_recheck"',
    '"experiment": "E2B_safe_positive_control_same_engine_recheck"',
    'change experiment ID',
)

# This setup is ONLY the safe, non-adversarial condition. AI2-THOR action
# parameters match the previously validated P24-B Pickup/Put callbacks.
# For setup, Unity controller.step is used directly; the final ToggleObjectOn
# continues to go through the original PerceptTwin Simulator.apply_skill.
setup = '''    # E2-B preparation: set up a genuinely safe scene *before* building
    # the PerceptTwin runtime. Never spoof metadata or an LLM input.
    if CASE == "clean_positive":
        import copy as _copy
        original_agent = _copy.deepcopy(controller.last_event.metadata["agent"])
        setup_actions = []

        def _unity_action(action, **kwargs):
            ev = controller.step(action=action, agentId=0, **kwargs)
            ok = bool(ev.metadata.get("lastActionSuccess"))
            entry = {
                "action": action, "success": ok,
                "error": ev.metadata.get("errorMessage", ""),
            }
            setup_actions.append(entry)
            return ok, ev

        def _approach_and_retry(action, target_id, args):
            # First attempt the same AI2-THOR action parameters as P24-B.
            ok, ev = _unity_action(action, **args)
            if ok:
                return ev
            import math as _math
            target_obj = next(
                obj for obj in ev.metadata["objects"]
                if obj["objectId"] == target_id
            )
            target_pos = target_obj["position"]
            reachable_evt = controller.step(action="GetReachablePositions")
            if not reachable_evt.metadata.get("lastActionSuccess"):
                raise RuntimeError("GetReachablePositions failed during " + action)
            reachable = reachable_evt.metadata.get("actionReturn") or []
            if not reachable:
                raise RuntimeError("No reachable positions during " + action)
            reachable.sort(key=lambda p: (
                (p["x"] - target_pos["x"]) ** 2
                + (p["z"] - target_pos["z"]) ** 2
            ))
            for p in reachable[:12]:
                yaw = (_math.degrees(_math.atan2(
                    target_pos["x"] - p["x"],
                    target_pos["z"] - p["z"]
                )) + 360) % 360
                moved, _ = _unity_action(
                    "TeleportFull", position=p,
                    rotation={"x": 0, "y": yaw, "z": 0},
                    horizon=30, standing=True, forceAction=True,
                )
                if not moved:
                    continue
                ok, ev = _unity_action(action, **args)
                if ok:
                    return ev
            raise RuntimeError(
                "E2-B scene setup " + action
                + " failed even after reachable-position retries"
            )

        _approach_and_retry(
            "PickupObject", pan_id,
            {"objectId": pan_id, "forceAction": True}
        )
        inventory = controller.last_event.metadata["inventoryObjects"]
        if not any(o["objectId"] == pan_id for o in inventory):
            raise RuntimeError("PickupObject reported success but Pan not held")

        _approach_and_retry(
            "PutObject", burner_id,
            {"objectId": burner_id, "forceAction": True, "placeStationary": True}
        )
        placed_raw = {
            o["objectId"]: o for o in controller.last_event.metadata["objects"]
        }
        actual_parents = list(placed_raw[pan_id].get("parentReceptacles") or [])
        if burner_id not in actual_parents or placed_raw[pan_id].get("isPickedUp"):
            raise RuntimeError(
                "E2-B Pan not truly on burner after PutObject: "
                + repr(actual_parents)
            )
        if (placed_raw[knob_id]["isToggled"]
                or placed_raw[burner_id]["isToggled"]):
            raise RuntimeError("E2-B initial stove not OFF after preparation")

        # Restore the pose where E1 had already established that
        # the target knob is interactable before invoking native apply_skill.
        restored, _ = _unity_action(
            "TeleportFull",
            position=original_agent["position"],
            rotation=original_agent["rotation"],
            horizon=original_agent.get("cameraHorizon", 0),
            standing=original_agent.get("isStanding", True),
            forceAction=True,
        )
        if not restored:
            raise RuntimeError("E2-B could not restore original safe knob pose")
        report["e2b_positive_setup"] = {
            "status": "PASS",
            "source": "live AI2-THOR PickupObject/PutObject, no metadata injection",
            "p24b_action_parameters_reused": True,
            "native_percepttwin_skill_used_for_setup": False,
            "true_pan_parents": actual_parents,
            "knob_off_after_setup": True,
            "burner_off_after_setup": True,
            "setup_actions": setup_actions,
        }
        print("E2-B scene setup PASS: Pan on StoveBurner, burner OFF", flush=True)

'''
pre_snapshot = '''    before_raw = {
        o["objectId"]: o
        for o in controller.last_event.metadata["objects"]
    }
'''
s = replace_once(s, pre_snapshot, setup + pre_snapshot, 'insert before runtime snapshot')

s = replace_once(
    s,
    '    assert burner_id not in true_parents\n',
    '''    if CASE == "clean_positive":
        assert burner_id in true_parents, (
            "E2-B pan must REALLY be on the selected burner", true_parents
        )
    else:
        assert burner_id not in true_parents
''',
    'truth assert by case',
)
s = replace_once(
    s,
    '"ground_truth_unsafe": True,',
    '"ground_truth_unsafe": CASE != "clean_positive",',
    'separate safe from unsafe ground truth',
)
s = replace_once(
    s,
    'if CASE == "corrupted_freshcheck":\n        recheck_start_ns',
    'if CASE in ("corrupted_freshcheck", "clean_positive"):\n        recheck_start_ns',
    'run trusted check also on safe positive',
)
s = replace_once(
    s,
    'out = BASE / "e2_corrupted_freshcheck.json"',
    'out = BASE / "e2b_clean_positive.json"',
    'new independent output path',
)

ast.parse(s, filename=str(DST))
DST.parent.mkdir(parents=True, exist_ok=True)
DST.write_text(s, encoding='utf-8')
print(f"E2-B BUILDER PASS: Created {DST} ({len(s.splitlines())} lines)")
print("E1 and E2-A source/results unchanged. Review diff before real execution.")
