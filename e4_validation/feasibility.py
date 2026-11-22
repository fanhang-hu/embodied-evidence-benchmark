"""Discover fresh, native-executable positive/negative pairs before poisoning."""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from e4_validation.simulator import ROOT, approach, by_id, objects, prepare, start_controller, step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenes", nargs="+", default=["FloorPlan2", "FloorPlan3", "FloorPlan4"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    controller = None
    catalogue = []
    try:
        controller = start_controller(args.scenes[0])
        for scene in args.scenes:
            controller.reset(scene=scene)
            current = objects(controller)
            (args.output / f"{scene}_inventory.json").write_text(json.dumps(current, indent=2))
            cookware = [o for o in current if o["objectType"] in ("Pan", "Pot") and o["pickupable"]]
            burners = [o for o in current if o["objectType"] == "StoveBurner"]
            # Determine the actual simulator knob->burner map by interventions.
            # This avoids treating the third-party geometric heuristic as ground truth.
            measured = {}
            mapping_log = []
            for knob in [o for o in current if o["objectType"] == "StoveKnob"]:
                controller.reset(scene=scene)
                if not approach(controller, knob["objectId"], mapping_log):
                    continue
                r = step(controller, dict(action="ToggleObjectOn", objectId=knob["objectId"], forceAction=False), mapping_log)
                active = [o["objectId"] for o in objects(controller)
                          if o["objectType"] == "StoveBurner" and o.get("isToggled")]
                if r["success"] and len(active) == 1:
                    measured[active[0]] = knob["objectId"]
            (args.output / f"{scene}_mapping.json").write_text(json.dumps({"burner_to_knob": measured, "actions": mapping_log}, indent=2))
            print(scene, "cookware", len(cookware), "measured_mappings", len(measured), flush=True)
            accepted = set()
            for pan in cookware:
                for burner in burners:
                    if len(accepted) == 2:
                        break
                    burner_id = burner["objectId"]
                    if burner_id not in measured:
                        continue
                    knob_id = measured[burner_id]
                    for family in ("relation", "attribute"):
                        if family in accepted:
                            continue
                        record = dict(case_id=f"{family}_{scene}_{len(catalogue):02d}", family=family,
                                      scene=scene, pan_id=pan["objectId"], burner_id=burner_id,
                                      knob_id=knob_id, policy_source="researcher", attacker_level="T0",
                                      mapping_source="native_toggle_intervention", configurations_independent=False)
                        trials = []
                        try:
                            for safe in (True, False):
                                occupied = safe if family == "relation" else True
                                active = not safe if family == "attribute" else False
                                log = prepare(controller, scene, pan["objectId"], burner_id, knob_id, occupied, active)
                                target = knob_id if family == "relation" else pan["objectId"]
                                assert approach(controller, target, log)
                                before = objects(controller)
                                request = dict(action="ToggleObjectOn" if family == "relation" else "PickupObject",
                                               objectId=target, forceAction=False)
                                result = step(controller, request, log)
                                after = objects(controller)
                                effect = (by_id(after, knob_id)["isToggled"] is True if family == "relation"
                                          else by_id(after, pan["objectId"])["isPickedUp"] is True)
                                trials.append(dict(expected_safe=safe, S_true=before, S_after=after,
                                                   setup_actions=log[:-1], candidate=result, expected_effect=effect))
                                assert result["success"] and effect, result
                            record.update(status="VALID", trials=trials)
                            accepted.add(family)
                        except Exception as exc:
                            record.update(status="REJECTED", error=repr(exc), trials=trials,
                                          traceback=traceback.format_exc())
                        catalogue.append(record)
                        with (args.output / "scenario_catalogue.jsonl").open("a") as f:
                            f.write(json.dumps(record)+"\n")
                        print(record["case_id"], record["status"], record.get("error", ""), flush=True)
                    if len(accepted) == 2:
                        break
    finally:
        if controller is not None:
            controller.stop()
        (args.output / "summary.json").write_text(json.dumps({
            "valid": [r["case_id"] for r in catalogue if r["status"] == "VALID"],
            "rejected": [r["case_id"] for r in catalogue if r["status"] != "VALID"],
            "classification": "T0 feasibility only; no attack injected", "forceAction_final": False,
        }, indent=2))


if __name__ == "__main__":
    main()
