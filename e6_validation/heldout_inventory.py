"""Preselect new E6 scenes, then calibrate physical contracts without attacks."""
from __future__ import annotations

import argparse
import datetime
import json

from e4_validation.protocol import fact, obj
from e4_validation.simulator import objects, prepare, start_controller
from e5_validation.common import CATALOGUE, ROOT, file_sha, finish_hashes, read_jsonl, state, write_json
from e6_validation.producer_experiment import new_directory


def target_candidates(items):
    cookware = sorted((o for o in items if o["objectType"] in {"Pan", "Pot"}),
                      key=lambda o: (o["objectType"] != "Pan", o["objectId"]))
    burners = {o["objectId"]: o for o in items if o["objectType"] == "StoveBurner"}
    pairs = sorted((knob["objectId"], target) for knob in items if knob["objectType"] == "StoveKnob"
                   for target in knob.get("controlledObjects") or []
                   if target in burners and not burners[target].get("receptacleObjectIds"))
    if not cookware or not pairs:
        raise ValueError("No cookware and exact controlled empty burner pair")
    return [dict(pan_id=cookware[0]["objectId"], knob_id=knob, burner_id=burner)
            for knob, burner in pairs]


def choose_targets(items):
    return target_candidates(items)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes", nargs="+", default=["FloorPlan9", "FloorPlan10"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    development = {c["scene"] for c in read_jsonl(ROOT / CATALOGUE)}
    if set(args.scenes).intersection(development) or len(set(args.scenes)) != len(args.scenes):
        raise ValueError("Heldout scenes must be distinct and absent from E6 development")
    out = new_directory(args.out)
    write_json(out / "selection_protocol.json", dict(
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), scenes=args.scenes,
        excluded_development_scenes=sorted(development),
        selection_rule="First Pan (else Pot), then first lexicographic exact controlled empty burner pair passing native calibration",
        eligibility_rule="Native on/off and exact placement only; no attack/defense/planner outcomes used",
        source_sha256={p: file_sha(ROOT / p) for p in ("e6_validation/heldout_inventory.py", "e4_validation/simulator.py", str(CATALOGUE))}))
    controller, cases, calibrations = None, [], []
    try:
        controller = start_controller(args.scenes[0])
        for scene in args.scenes:
            result = dict(scene=scene)
            try:
                controller.reset(scene=scene)
                initial = state(objects(controller))
                result["initial"] = initial
                attempts = []
                result["candidate_calibrations"] = attempts
                for targets in target_candidates(initial["objects"]):
                    attempt = dict(targets=targets)
                    try:
                        base = dict(scene=scene, **targets)
                        receipts_off = prepare(controller, scene, **targets, occupied=True, active=False)
                        off = state(objects(controller))
                        relation_case = dict(base, family="relation")
                        if not fact(off, relation_case):
                            raise ValueError("Native placement does not satisfy exact membership")
                        receipts_on = prepare(controller, scene, **targets, occupied=True, active=True)
                        on = state(objects(controller))
                        if (not obj(on, targets["knob_id"])["isToggled"] or
                                not obj(on, targets["burner_id"])["isToggled"]):
                            raise ValueError("Native knob/burner control not confirmed")
                        attempt["status"] = "ELIGIBLE"
                        attempts.append(attempt)
                        break
                    except Exception as exc:
                        attempt.update(status="INELIGIBLE", error=repr(exc))
                        attempts.append(attempt)
                else:
                    raise ValueError("No prespecified candidate passed native calibration")
                result.update(status="ELIGIBLE", initial=initial, off=off, on=on,
                              receipts_off=receipts_off, receipts_on=receipts_on, targets=targets)
                for family in ("attribute", "relation"):
                    cases.append(dict(base, family=family, case_id=f"heldout_{family}_{scene}_01",
                                      split="heldout", calibration_scene=scene,
                                      heldout_definition="Scene disjoint from existing E6 development catalogue"))
            except Exception as exc:
                result.update(status="INELIGIBLE", error=repr(exc))
            calibrations.append(result)
            write_json(out / f"calibration_{scene}.json", result)
    finally:
        if controller is not None:
            controller.stop()
        with (out / "cases.jsonl").open("w", encoding="utf-8") as handle:
            for case in cases:
                handle.write(json.dumps(case)+"\n")
        write_json(out / "summary.json", dict(
            status="COMPLETE" if len(cases) == 2*len(args.scenes) else "INCOMPLETE",
            selected_scenes=args.scenes, eligible_scenes=[r["scene"] for r in calibrations if r["status"] == "ELIGIBLE"],
            independent_scene_clusters=len({c["scene"] for c in cases}), cases=len(cases),
            planner_calls=0, attack_episodes=0,
            source="native_metadata_privileged_setup_and_unforced_knob_control"))
        finish_hashes(out)
    if len(cases) != 2*len(args.scenes):
        raise RuntimeError("Prespecified scene calibration incomplete; retain all failures")
    print(out / "cases.jsonl")


if __name__ == "__main__":
    main()
