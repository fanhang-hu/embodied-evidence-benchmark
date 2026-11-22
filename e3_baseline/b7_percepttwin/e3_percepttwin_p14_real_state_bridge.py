import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import jax.numpy as jnp
from pathlib import Path

from hippo.simulation.runtimeobjects import RuntimeObject, RuntimeObjectContainer
from hippo.simulation.skillsandconditions.skill_names import canonical_enabledname_2_llmname
from hippo.simulation.skill_simulator import Simulator
from hippo.simulation.singlefilelog import set_filepath

BASE = Path("results/E3/07_percepttwin")
trace = json.loads((BASE / "p13_real_unity_trace.json").read_text())

assert trace["status"] == "PASS", "P13 did not pass"
assert trace["lastActionSuccess"] is True

knob_id = trace["target_object_id"]
burner_id = next(
    x["objectId"]
    for x in trace["burner_changes"]
    if x["before_isToggled"] is False
    and x["after_isToggled"] is True
)

IDS = [knob_id, burner_id]
SKILL_MAP = canonical_enabledname_2_llmname()

def build_container(snapshot):
    source = {
        x["objectId"]: x
        for x in trace[snapshot + "_objects"]
    }

    objects = {}

    for oid in IDS:
        raw = source[oid]

        d = {
            "id": oid,
            "position": raw["axisAlignedBoundingBox"]["center"],
            "rotation": raw["rotation"],
            "size": raw["axisAlignedBoundingBox"]["size"],
            "_skill_metadata": [
                name for flag, name in SKILL_MAP.items()
                if raw.get(flag, False)
            ],
        }

        obj = RuntimeObject.fromdict(d)

        # Preserve actual Unity attributes, including indirect
        # StoveBurner changes caused by ToggleObjectOn(StoveKnob).
        facts = {
            "object_name": raw["objectType"],
            "objectType": raw["objectType"],
            "isToggled": raw["isToggled"],
            "toggleable": raw.get("toggleable", False),
        }

        for key in ("temperature", "parentReceptacles",
                    "receptacleObjectIds"):
            if key in raw:
                facts[key] = raw[key]

        objects[oid] = obj.replace(metadata=facts)

    z = jnp.zeros((2, 2), dtype=bool)

    return RuntimeObjectContainer(
        object_names=IDS,
        objects_map=objects,
        robot_names=[],
        robots_map={},
        obj_isOnTopOf=z,
        obj_isInsideOf=z,
        obj_isBesideOf=z,
        obj_distances=jnp.zeros((2, 2), dtype=jnp.float32),
    )

before = build_container("before")
after = build_container("after")

before_view = before.as_llmjson()
after_view = after.as_llmjson()

for oid in IDS:
    assert before_view[oid]["isToggled"] is False, oid
    assert after_view[oid]["isToggled"] is True, oid

set_filepath(str(BASE / "p14_native_scene_log.jsonl"))

sim = Simulator(
    controller=None,
    no_robots=1,
    objects=before,
    full_reachability_graph=None,
    feedback_cfg={"audits": False},
)

action = (
    f'ToggleObjectOn(robot="robot0", '
    f'target_object="{knob_id}")'
)

sim.append_object_container(after)
sim.done_actions.append(action)

diff = sim.get_object_container_diff()

assert knob_id in diff
assert burner_id in diff
assert diff.count('-    "isToggled": false') == 2
assert diff.count('+    "isToggled": true') == 2

result = {
    "experiment": "P14_real_Unity_to_native_PerceptTwin",
    "source": "p13_real_unity_trace.json",
    "source_status": trace["status"],
    "action": action,
    "knob_id": knob_id,
    "burner_id": burner_id,
    "before": before_view,
    "after": after_view,
    "native_diff": diff,
    "state_source": "actual_Unity_metadata",
    "metadata_projection": True,
    "synthetic_safety_facts": False,
    "planner_executed": False,
    "llm_audit_executed": False,
}

out = BASE / "p14_real_state_bridge.json"
out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

print("=== P14 REAL STATE BRIDGE ===")
print("Knob:", knob_id)
print("Burner:", burner_id)
print("Unity -> PerceptTwin mapping: PASS")
print("Knob OFF -> ON: PASS")
print("Burner OFF -> ON: PASS")
print("Native diff verification: PASS")

print("\n=== Cookware in actual scene ===")
for o in trace["before_objects"]:
    if o.get("objectType") in ("Pan", "Pot"):
        print(
            o["objectType"],
            o["objectId"],
            "parentReceptacles=",
            o.get("parentReceptacles"),
        )

print("\nSaved:", out)
print("P14 PASS")
