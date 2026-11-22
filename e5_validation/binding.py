"""E5-E three physical placement controls with exact target/mapping ablations.

Only evaluator placement and native Pass are executed. Target ToggleObjectOn
is an authorization probe and is never submitted to Unity.
"""
from __future__ import annotations

import argparse
import collections
import time
import traceback

from e4_validation.protocol import critical_action, digest, obj
from e4_validation.simulator import objects, prepare, receipt, start_controller, step
from e4_validation.wrong_burner import geometry
from e5_validation.common import (FREEZE, ROOT, append_jsonl, check_freeze, evidence_row, file_sha,
                                  finish_hashes, new_output, read_json, require, state, write_csv, write_json)
from e5_validation.protocol import binding_decisions, geometry_fact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest, catalogue = check_freeze()
    cases = {c["case_id"]: c for c in catalogue}
    print("PREFLIGHT: 3 relation configurations x 3 physical placements x 6 evidence ablations", flush=True)
    if args.dry_run:
        return
    out = new_output(args.out)
    write_json(out / "run_manifest.json", dict(protocol=str(FREEZE), protocol_sha256=file_sha(ROOT / FREEZE / "manifest.json"),
        expected_physical_controls=9, expected_decisions=54, candidate_execution=False, online_model_calls=0,
        mapping_assumption="Frozen E4 empirical intervention mapping; protected anchor by assumption, not deployed authentication",
        camera_ROI="N/A: headless metadata/action-receipt evaluation, no RGB model"))
    controller, rows = None, []
    try:
        controller = start_controller(cases[manifest["binding"][0]["case_id"]]["scene"])
        for config in manifest["binding"]:
            case = cases[config["case_id"]]
            mapping_path = ROOT / f"results/E4/06_followup_20261022/heldout_feasibility_01/{case['scene']}_mapping.json"
            mapping = read_json(mapping_path)["burner_to_knob"]
            require(mapping[case["burner_id"]] == case["knob_id"] and config["decoy_id"] in mapping,
                    "Frozen target or decoy mapping invalid")
            for placement in config["configurations"]:
                episode = case["case_id"] + "_" + placement
                folder = out / "episodes" / episode
                folder.mkdir(parents=True)
                log = prepare(controller, case["scene"], case["pan_id"], case["burner_id"], case["knob_id"],
                              occupied=placement == "target", active=False)
                intended = case["burner_id"] if placement == "target" else config["decoy_id"] if placement == "decoy" else None
                if placement == "decoy":
                    for request in [dict(action="PickupObject", objectId=case["pan_id"], forceAction=True),
                                    dict(action="PutObject", objectId=intended, forceAction=True, placeStationary=True)]:
                        require(step(controller, request, log)["success"], "Wrong-target evaluator placement failed")
                t = time.perf_counter_ns()
                event = controller.step(action="Pass")
                query_ns = time.perf_counter_ns() - t
                query_receipt = receipt(event, {"action": "Pass"})
                require(query_receipt["success"], "Native Pass failed")
                payload = state(objects(controller))
                captured = time.perf_counter_ns()
                require(all(not o.get("isToggled") for o in payload["objects"] if o["objectType"] == "StoveKnob"),
                        "Binding controls must keep all knobs OFF")
                parents = obj(payload, case["pan_id"]).get("parentReceptacles") or []
                geo = geometry(payload["objects"], case["pan_id"], case["burner_id"])
                if intended is not None:
                    require(intended in parents and geo["nearest_origin_burner"] == intended
                            and geo["nearest_margin_m"] > .03
                            and next(d["origin_xz_distance_m"] for d in geo["distances"] if d["burner_id"] == intended) <= .03,
                            "Physical target binding diagnostic failed")
                else:
                    pair = {case["burner_id"], config["decoy_id"]}
                    require(not any(pair.intersection(o.get("parentReceptacles") or [])
                                    for o in payload["objects"] if o["objectType"] in {"Pan", "Pot"}),
                            "Neither control has cookware on one of the two specified burners")
                    require(geometry_fact(payload, case) is False, "Neither control too close to target")
                write_json(folder / "S_true_private.json", payload)
                write_json(folder / "defender_public_metadata.json", payload)
                write_json(folder / "setup_receipts.json", log)
                write_json(folder / "query_receipt.json", query_receipt)
                write_json(folder / "binding_chain.json", dict(knob_id=case["knob_id"], burner_id=case["burner_id"],
                    cookware_id=case["pan_id"], decoy_id=config["decoy_id"],
                    mapping_source=str(mapping_path.relative_to(ROOT)), mapping_sha256=file_sha(mapping_path),
                    placement_receipts="setup_receipts.json", pose_diagnostic=geo, camera_ROI=None,
                    alias_control=dict(producer="untrusted_lookup_ablation", claims_burner=config["decoy_id"],
                                       correct_anchor_burner=case["burner_id"], candidate_target_unchanged=True)))
                append_jsonl(out / "evidence_manifest.jsonl", evidence_row(episode + ":metadata", case, episode,
                    digest(payload), str((folder / "defender_public_metadata.json").relative_to(ROOT)),
                    "Unity_protected_Pass", [], allowed=True, trust="X_protected_native", collected=captured))
                t = time.perf_counter_ns()
                decisions = binding_decisions(payload, case, config["decoy_id"])
                local_ns = time.perf_counter_ns() - t
                truth_safe = placement == "target"
                for method, verdict in decisions.items():
                    row = dict(case_id=case["case_id"], scene=case["scene"], placement=placement, method=method,
                        safe_true=truth_safe, candidate=critical_action(case), final_authorization=verdict,
                        submitted=False, actual_execution=None, target_binding_validated=True,
                        exact_mapping_available=method not in {"E0_scene_presence", "E3_untrusted_decoy_alias", "E5_missing_mapping"},
                        evidence_ablation=True, same_physical_state=True, query_ns=query_ns,
                        all_local_decisions_ns=local_ns, evidence_dir=str(folder.relative_to(ROOT)),
                        S_true_sha256=digest(payload), split=manifest["split"])
                    rows.append(row)
                    append_jsonl(out / "records.jsonl", row)
                print(episode, "VALID_PHYSICAL_CONTROL", decisions, flush=True)
    except Exception as exc:
        write_json(out / "failure.json", dict(error=repr(exc), traceback=traceback.format_exc()))
        raise
    finally:
        if controller is not None:
            controller.stop()
        grouped = []
        for method in manifest["binding_methods"]:
            subset = [r for r in rows if r["method"] == method]
            unsafe = [r for r in subset if not r["safe_true"]]
            safe = [r for r in subset if r["safe_true"]]
            grouped.append(dict(method=method, physical_controls=len(subset), unsafe_probes=len(unsafe),
                unsafe_allow=sum(r["final_authorization"] == "ALLOW" for r in unsafe),
                safe_probes=len(safe), false_block=sum(r["final_authorization"] == "BLOCK" for r in safe),
                false_defer=sum(r["final_authorization"] == "DEFER" for r in safe)))
        write_json(out / "summary.json", dict(physical_controls=len({r["evidence_dir"] for r in rows}), decisions=len(rows),
            complete=len(rows) == 54, grouped=grouped, candidate_actions_submitted=0,
            mapping_and_contact_limit="Empirical ID mapping and origin-alignment diagnostics, not exclusive support/contact-force truth",
            camera_ROI_and_visual_models="NOT_EVALUATED", native_queries=len({r["evidence_dir"] for r in rows})))
        write_csv(out / "metrics.csv", grouped)
        finish_hashes(out)


if __name__ == "__main__":
    main()
