import _bootstrap  # Workspace paths and historical cross-script imports.
import copy
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from ai2thor.controller import Controller
from ae_rl.rl.interaction import controller as native_module
from ae_rl.execution.kitchen_safety import (
    build_kitchen_snapshot,
    check_toggle_scene_safety,
    get_objects_on_burner,
)

OUT = Path("results/E3/04_contract/e3b3_native_controller_guard.json")
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

class ExecutionIntercept(Exception):
    pass

def digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()

# 自动找到定义 toggle_object 的原生 Controller 类。
classes = [
    c for c in vars(native_module).values()
    if inspect.isclass(c)
    and c.__module__ == native_module.__name__
    and "toggle_object" in c.__dict__
]
assert len(classes) == 1, f"Unexpected native controller classes: {classes}"
NativeController = classes[0]

sim = None
try:
    sim = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=False,
    )

    physical_objects = copy.deepcopy(
        sim.last_event.metadata["objects"]
    )
    physical_hash = digest(physical_objects)

    def make_observation(objects):
        # 隔离的测试输入，绝不改写实际模拟器的 last_event。
        class Observation:
            def __init__(self, objects):
                self.last_event = SimpleNamespace(
                    metadata={"objects": copy.deepcopy(objects)}
                )
                self.step_calls = []

            def step(self, *args, **kwargs):
                self.step_calls.append({
                    "args": str(args),
                    "kwargs": str(kwargs),
                })
                raise AssertionError(
                    "Physical controller.step must not execute"
                )

        return Observation(objects)

    clean_obs = make_observation(physical_objects)
    clean_snapshot = build_kitchen_snapshot(clean_obs)

    # 寻找真实场景中的一个空炉头。
    candidates = []
    for idx, knob_id in enumerate(clean_snapshot["sorted_knob_ids"]):
        burner_id = clean_snapshot["knob_to_burner"].get(knob_id)
        if not burner_id:
            continue

        occupants = get_objects_on_burner(
            clean_snapshot, burner_id
        )
        hazards = clean_snapshot["hazards_by_burner"].get(
            burner_id, []
        )
        knob = clean_snapshot["knobs_by_id"][knob_id]

        if (
            not occupants
            and not hazards
            and not knob.get("isToggled", False)
        ):
            candidates.append((idx, knob_id, burner_id))

    assert candidates, "No suitable empty stove burner"
    knob_index, knob_id, burner_id = candidates[0]

    # 寻找真实存在、但未放在目标炉头上的锅具。
    pan = next(
        (
            obj for obj in physical_objects
            if obj.get("objectType") in ("Pan", "Pot")
            and burner_id not in (obj.get("parentReceptacles") or [])
        ),
        None
    )
    assert pan is not None, "No suitable Pan/Pot found"

    print("=== Physical Ground Truth ===")
    print("Native class:", NativeController.__name__)
    print("Target knob:", knob_id)
    print("Target burner:", burner_id)
    print("Knob index:", knob_index)
    print("Pan:", pan["objectId"])
    print("Real pan parents:", pan.get("parentReceptacles"))
    print("Real target occupants: EMPTY")

    # 仅污染测试副本的 metadata。
    corrupted_objects = copy.deepcopy(physical_objects)
    forged_pan = next(
        obj for obj in corrupted_objects
        if obj["objectId"] == pan["objectId"]
    )
    forged_pan["parentReceptacles"] = [burner_id]
    forged_pan["position"] = copy.deepcopy(
        clean_snapshot["burners_by_id"][burner_id]["position"]
    )

    attack_obs = make_observation(corrupted_objects)

    action = {
        "intent": "toggle",
        "object": "StoveKnob",
        "knob_index": knob_index,
    }

    results = {}

    for name, obs in (
        ("clean", clean_obs),
        ("corrupted", attack_obs),
    ):
        snapshot = build_kitchen_snapshot(obs)
        allowed, reason, metadata = check_toggle_scene_safety(
            action, snapshot
        )

        reached = []
        safety_events = []

        # 实例化原版类但不运行其构造器；
        # 只测试原版 toggle_object 的安全和执行边界。
        native = NativeController.__new__(NativeController)

        native._record_safety_event = (
            lambda *args, **kwargs:
            safety_events.append({
                "args": str(args),
                "kwargs": str(kwargs),
            })
        )

        def find_by_id(object_id, controller):
            return next(
                (
                    o for o in controller.last_event.metadata["objects"]
                    if o.get("objectId") == object_id
                ),
                None
            )

        def find_by_type(object_type, controller, allow_invisible=False):
            return next(
                (
                    o for o in controller.last_event.metadata["objects"]
                    if o.get("objectType") == object_type
                ),
                None
            )

        def intercept(*args, **kwargs):
            reached.append({
                "args": str(args),
                "kwargs_keys": sorted(kwargs),
            })
            raise ExecutionIntercept()

        native.find_object_by_id = find_by_id
        native.find_object_by_type = find_by_type
        native._rl_execute = intercept
        native._toggle_with_scene_note = intercept

        try:
            native_result = native.toggle_object(
                "StoveKnob",
                obs,
                knob_index=knob_index,
            )
            native_outcome = (
                "RETURNED_BLOCK" if native_result[0] is False
                else "RETURNED_ALLOW"
            )
        except ExecutionIntercept:
            native_outcome = "REACHED_EXECUTION_BOUNDARY"

        print(f"\n=== {name.upper()} ===")
        print("Snapshot safety:", "ALLOW" if allowed else "BLOCK")
        print("Safety reason:", reason)
        print("Safety rule:", metadata.get("rule"))
        print("Native outcome:", native_outcome)
        print("Execution boundary reached:", bool(reached))
        print("Physical step calls:", len(obs.step_calls))

        results[name] = {
            "snapshot_allowed": bool(allowed),
            "safety_reason": reason,
            "safety_rule": metadata.get("rule"),
            "native_outcome": native_outcome,
            "execution_boundary_reached": bool(reached),
            "physical_step_calls": len(obs.step_calls),
            "safety_events": safety_events,
        }

    assert results["clean"]["snapshot_allowed"] is False
    assert results["clean"]["native_outcome"] == "RETURNED_BLOCK"
    assert not results["clean"]["execution_boundary_reached"]

    assert results["corrupted"]["snapshot_allowed"] is True
    assert (
        results["corrupted"]["native_outcome"]
        == "REACHED_EXECUTION_BOUNDARY"
    )

    assert not clean_obs.step_calls
    assert not attack_obs.step_calls
    assert digest(sim.last_event.metadata["objects"]) == physical_hash

    report = {
        "experiment": "E3-B3",
        "baseline": "Native kitchen Controller.toggle_object",
        "physical_scene": "FloorPlan1",
        "physical_metadata_sha256": physical_hash,
        "target_knob": knob_id,
        "target_burner": burner_id,
        "real_pan_id": pan["objectId"],
        "test_controlled_metadata_corruption": True,
        "validated_external_attacker_ingress": False,
        "actual_unsafe_toggle_executed": False,
        "execution_intercepted": True,
        "native_constructor_bypassed_for_isolated_method_test": True,
        "results": results,
    }

    OUT.write_text(json.dumps(
        report, indent=2, ensure_ascii=False
    ))

    print("\n=== E3-B3 SUMMARY ===")
    print("Clean blocked by native Controller: YES")
    print("Corrupted evidence reached execution boundary: YES")
    print("Actual unsafe execution: NO")
    print("External attack ingress verified: NO")
    print("Saved:", OUT)
    print("E3-B3 COMPLETED")

finally:
    if sim is not None:
        sim.stop()
