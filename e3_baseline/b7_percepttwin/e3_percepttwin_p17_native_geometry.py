import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path

from hippo.simulation.runtimeobjects import (
    RuntimeObject,
    RuntimeObjectContainer,
)
from hippo.simulation.skillsandconditions.skill_names import (
    canonical_enabledname_2_llmname,
)

BASE = Path("results/E3/07_percepttwin")
trace = json.loads((BASE / "p13_real_unity_trace.json").read_text())
bridge = json.loads((BASE / "p14_real_state_bridge.json").read_text())
p16 = json.loads((BASE / "p16_real_state_attack.json").read_text())

assert trace["status"] == "PASS"
assert len(p16) == 3

knob_id = bridge["knob_id"]
burner_id = bridge["burner_id"]

before = {o["objectId"]: o for o in trace["before_objects"]}
after = {o["objectId"]: o for o in trace["after_objects"]}

pan = next(o for o in before.values() if o["objectType"] == "Pan")
pan_id = pan["objectId"]

parents = pan.get("parentReceptacles") or []
assert len(parents) == 1
counter_id = parents[0]
assert before[counter_id]["objectType"] == "CounterTop"

# The original geometry resolver excludes its last entity,
# assuming that entity is a robot. Add a genuine additional
# scene object as the final element so the four objects being
# assessed are not affected by that implementation detail.
extra = next(
    o for o in before.values()
    if o["objectType"] in ("Fridge", "Microwave", "Cabinet")
    and o["objectId"] not in {
        knob_id, burner_id, pan_id, counter_id
    }
)
extra_id = extra["objectId"]

ids = [knob_id, burner_id, pan_id, counter_id, extra_id]
skill_map = canonical_enabledname_2_llmname()


def make_runtime(raw):
    d = {
        "id": raw["objectId"],
        "position": raw["axisAlignedBoundingBox"]["center"],
        "rotation": raw["rotation"],
        "size": raw["axisAlignedBoundingBox"]["size"],
        "_skill_metadata": [
            name for flag, name in skill_map.items()
            if raw.get(flag, False)
        ],
    }

    return RuntimeObject.fromdict(d).replace(
        metadata={"object_name": raw["objectType"]}
    )


def calculate(snapshot):
    objects = [make_runtime(snapshot[oid]) for oid in ids]

    # Official constructor: calculates spatial attributes
    # from positions and bounding boxes using native JAX code.
    container = RuntimeObjectContainer.create(objects)
    state = container.as_llmjson()

    return {
        "pan_on_top": state[pan_id]["isOnTopOf"],
        "pan_inside": state[pan_id]["isInsideOf"],
        "pan_distances": state[pan_id]["object_distances"],
    }


native_before = calculate(before)
native_after = calculate(after)

result = {
    "experiment": "P17_native_geometry_validation",
    "source": "P13_actual_Unity_metadata",
    "native_method": "RuntimeObjectContainer.create",
    "pan_id": pan_id,
    "counter_id": counter_id,
    "burner_id": burner_id,
    "additional_scene_object": extra_id,
    "unity_parentReceptacles": parents,
    "native_before": native_before,
    "native_after": native_after,
    "native_matches_unity_parent": (
        counter_id in native_before["pan_on_top"]
    ),
    "native_rejects_false_burner_relation": (
        burner_id not in native_before["pan_on_top"]
    ),
    "p16_decisions": {
        x["case"]: x["decision"] for x in p16
    },
    "llm_called": False,
    "unity_executed_in_this_run": False,
}

out = BASE / "p17_native_geometry.json"
out.write_text(json.dumps(result, indent=2))

print("=== P17 NATIVE GEOMETRY ===")
print("Unity Pan parent:", parents)
print("Native BEFORE isOnTopOf:", native_before["pan_on_top"])
print("Native AFTER isOnTopOf:", native_after["pan_on_top"])
print("Native matches Unity parent:",
      result["native_matches_unity_parent"])
print("Native excludes false burner relation:",
      result["native_rejects_false_burner_relation"])
print("P16 decisions:", result["p16_decisions"])
print("Saved:", out)
print("P17 COMPLETE")
