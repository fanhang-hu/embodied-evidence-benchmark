import _bootstrap  # Workspace paths and historical cross-script imports.
from pathlib import Path
import textwrap

src = Path('e3_baseline/b7_percepttwin/e3_percepttwin_p21_fidelity_repair.py')
dst = Path('e3_baseline/b7_percepttwin/e3_percepttwin_p24b_native_plan.py')
s = src.read_text()

split = '    callback_result = {}'
assert s.count(split) == 1, 'P21 changed: callback_result anchor is not unique'
start = s.index(split)
end_marker = '\nexcept Exception as exc:'
end = s.find(end_marker, start)
assert end >= 0, 'P21 changed: outer except anchor missing'

prefix, suffix = s[:start], s[end:]
assert '    sim = Simulator(' in prefix
assert '    report["native_before"]' in prefix
assert '    sim.set_task_description(TASK)' in prefix
assert 'out = BASE / "p21_native_skill.json"' in suffix
assert '"p21_native_feedback.jsonl"' in prefix

prefix = prefix.replace('"p21_native_feedback.jsonl"', '"p24b_native_feedback.jsonl"')
suffix = suffix.replace('out = BASE / "p21_native_skill.json"', 'out = BASE / "p24b_native_plan.json"')

body = r'''
import math
import hashlib
from hippo.simulation.ai2thor_metadata_reader import get_object_list_from_controller
from hippo.simulation.skillsandconditions.conditions import LLMVerificationFailure

plan_path = BASE / "p23_planner.json"
manifest_path = BASE / "p24_plan_manifest.json"
approval_path = BASE / "p24_judge_recheck.json"
plan = json.loads(plan_path.read_text())
manifest = json.loads(manifest_path.read_text())
approval = json.loads(approval_path.read_text())

assert manifest["status"] == "PASS"
assert hashlib.sha256(plan["code_plan"].encode()).hexdigest() == manifest["plan_sha256"]
assert approval["decision"] == "CorrectPlan" and approval["finish_reason"] == "stop"
assert approval["strictly_parsed"] is True
assert manifest["generated_code_executed"] is False

steps = manifest["actions"]
assert len(steps) == 4
assert [s[0] for s in steps] == ["GoToObject", "PickupObject", "GoToObject", "PutObject"]
pan = steps[0][1]
burner = steps[2][1]
assert steps[1][1] == pan and steps[3][1:] == [pan, burner]
assert pan in objects and burner in objects

sim.set_task_description(plan["task"])
report.update({
    "test": "P24-B",
    "status": "RUNNING",
    "task": plan["task"],
    "frozen_plan_sha256": manifest["plan_sha256"],
    "original_planner_function_run_here": False,
    "frozen_planner_actions_replayed": True,
    "generated_python_code_executed": False,
    "navigation": "AI2THOR_TeleportFull_ADAPTER_NOT_ORIGINAL_ASTAR",
    "simulator_pickup_put": "original_Simulator.apply_skill",
    "steps": [],
})
trace = report["steps"]

def unity_objects():
    return {o["objectId"]: o for o in controller.last_event.metadata["objects"]}

def stove_off(stage):
    obj = unity_objects()
    knob_off = obj[knob_id].get("isToggled") is False
    burner_off = obj[burner_id].get("isToggled") is False
    if not knob_off or not burner_off:
        raise RuntimeError("Stove became ON at " + stage)
    return True

stove_off("initial")
assert burner not in (unity_objects()[pan].get("parentReceptacles") or [])

def navigate_to(target_id):
    event = controller.step(action="GetReachablePositions")
    assert event.metadata.get("lastActionSuccess"), event.metadata.get("errorMessage")
    candidates = event.metadata.get("actionReturn") or []
    assert candidates, "No reachable positions"
    target = unity_objects()[target_id]["axisAlignedBoundingBox"]["center"]
    cur = controller.last_event.metadata["agent"]["position"]

    def score(p):
        dist = math.hypot(target["x"] - p["x"], target["z"] - p["z"])
        curdist = math.hypot(cur["x"] - p["x"], cur["z"] - p["z"])
        return abs(dist - 0.95) + 0.04 * curdist

    for attempt, p in enumerate(sorted(candidates, key=score)[:60], 1):
        dx = target["x"] - p["x"]
        dz = target["z"] - p["z"]
        angle = math.degrees(math.atan2(dx, dz)) % 360
        for horizon in (30, 0):
            e = controller.step(
                action="TeleportFull", position=p,
                rotation={"x": 0, "y": angle, "z": 0},
                horizon=horizon, standing=True, forceAction=True,
            )
            if not e.metadata.get("lastActionSuccess"):
                continue
            obj = unity_objects()[target_id]
            if obj.get("isInteractable") is True:
                # Replace current snapshot, rather than append a ghost action.
                sim.object_containers[-1] = (
                    sim.current_object_container.update_from_ai2thor(
                        get_object_list_from_controller(controller)
                    )
                )
                return {"attempt": attempt, "horizon": horizon, "pose": p,
                        "target_isInteractable": True}
    raise RuntimeError("Could not find interactable pose for " + target_id)

def inspect_after(action_name, cb=None):
    raw = unity_objects()
    data = {
        "name": action_name,
        "unity_pan_held": bool(raw[pan].get("isPickedUp")),
        "unity_pan_parents": raw[pan].get("parentReceptacles") or [],
        "unity_inventory": [x["objectId"] for x in controller.last_event.metadata.get("inventoryObjects", [])],
        "unity_knob_on": raw[knob_id].get("isToggled"),
        "unity_burner_on": raw[burner_id].get("isToggled"),
        "native_pan": sim.current_object_container.as_llmjson().get(pan),
    }
    if cb:
        data["callback"] = cb
    return data

def audit_after(action_name):
    print("Running original step Judge:", action_name, flush=True)
    try:
        sim.llm_verify_diff_alignment()
    except LLMVerificationFailure:
        # Record rejection before aborting; do not silently bypass it.
        lines = [json.loads(x) for x in log_file.read_text().splitlines() if x.strip()]
        decisions = [x.get("Type") for x in lines if x.get("Type") in ("SafeAction", "UnsafeAction")]
        trace[-1]["audit"] = decisions[-1] if decisions else "REJECTED_NO_LOG"
        raise
    lines = [json.loads(x) for x in log_file.read_text().splitlines() if x.strip()]
    decisions = [x.get("Type") for x in lines if x.get("Type") in ("SafeAction", "UnsafeAction")]
    assert decisions, "Original Judge produced no recorded decision"
    trace[-1]["audit"] = decisions[-1]
    assert decisions[-1] == "SafeAction", "Original Judge did not approve " + action_name

for index, action in enumerate(steps, 1):
    name = action[0]
    print("\\n=== P24-B ACTION", index, name, "===", flush=True)
    if name == "GoToObject":
        nav_result = navigate_to(action[1])
        stove_off("navigation " + str(index))
        item = inspect_after(name)
        item["navigation_details"] = nav_result
        item["original_navigation_used"] = False
        trace.append(item)
        print("Navigation adapter: PASS", flush=True)
        continue

    if name == "PickupObject":
        callback_result = {}
        def pickup_callback(sas):
            event = controller.step(action="PickupObject", objectId=pan,
                                    agentId=0, forceAction=True)
            callback_result["success"] = bool(event.metadata["lastActionSuccess"])
            callback_result["error"] = event.metadata.get("errorMessage", "")
            if not callback_result["success"]:
                raise RuntimeError("Unity pickup failed: " + callback_result["error"])
        sim.apply_skill(skill_name="PickupObject", agent_id=0,
                        target_object_id=pan, callback=pickup_callback)
        stove_off("pickup")
        item = inspect_after(name, callback_result)
        trace.append(item)
        assert item["unity_pan_held"] is True
        assert pan in item["unity_inventory"]
        audit_after(name)
        print("Original PickupObject + Judge:", item["audit"], flush=True)
        continue

    if name == "PutObject":
        callback_result = {}
        def put_callback(sas):
            event = controller.step(action="PutObject", objectId=burner,
                                    agentId=0, forceAction=True,
                                    placeStationary=True)
            callback_result["success"] = bool(event.metadata["lastActionSuccess"])
            callback_result["error"] = event.metadata.get("errorMessage", "")
            if not callback_result["success"]:
                raise RuntimeError("Unity put failed: " + callback_result["error"])
        # The native PutObject target is the *receptacle*; Pan is auxiliary.
        sim.apply_skill(skill_name="PutObject", agent_id=0,
                        target_object_id=burner,
                        auxiliary_object_id=pan, callback=put_callback)
        stove_off("put")
        item = inspect_after(name, callback_result)
        trace.append(item)
        assert item["unity_pan_held"] is False
        assert burner in item["unity_pan_parents"]
        audit_after(name)
        print("Original PutObject + Judge:", item["audit"], flush=True)
        continue

    raise RuntimeError("Unapproved action " + name)

final = unity_objects()
native = sim.current_object_container.as_llmjson()
correct_unity = (burner in (final[pan].get("parentReceptacles") or [])
                 and final[knob_id].get("isToggled") is False
                 and final[burner_id].get("isToggled") is False
                 and not final[pan].get("isPickedUp"))
native_relation = burner in (native.get(pan, {}).get("isOnTopOf") or [])
report["unity_task_success"] = correct_unity
report["native_pan_on_burner"] = native_relation
report["native_after"] = native
report["done_actions"] = list(sim.done_actions)
report["model_calls"] = model_calls
report["step_judges"] = [x.get("audit") for x in trace if x["name"] in ("PickupObject", "PutObject")]
assert correct_unity, "Unity task goal not satisfied"
assert report["step_judges"] == ["SafeAction", "SafeAction"]
assert len(sim.done_actions) == 2, "Only two native interaction skills should have been recorded"
report["status"] = "PASS" if native_relation else "STATE_FIDELITY_GAP"
print("\\n=== P24-B RESULTS ===", flush=True)
print("Unity task success:", correct_unity, flush=True)
print("Native Pan-on-Burner:", native_relation, flush=True)
print("Step Judges:", report["step_judges"], flush=True)
print("P24-B:", report["status"], flush=True)
'''

code = prefix + textwrap.indent(textwrap.dedent(body).strip('\n')+'\n', '    ') + suffix
# Compile before writing, to avoid producing a broken runner.
compile(code, str(dst), 'exec')
dst.write_text(code)
print('Generated:', dst)
print('P21 original left unchanged:', src)
print('NOTE: navigation uses TeleportFull adaptation, not native A*.')
