"""Live paired episodes; one new output directory per invocation, no overwrite."""
from __future__ import annotations

import argparse
import copy
import json
import os
import stat
import time
import traceback
from pathlib import Path

from e4_validation.protocol import (CONDITIONS, canonical, critical_action, digest, fact,
                                    field_diff, monitor, plan, placebo, poison)
from e4_validation.simulator import ROOT, approach, by_id, objects, prepare, start_controller, step


def payload(controller, version):
    return dict(schema="e4.observation.v1", source_id="explicit_T0_adapter",
                state_version=version, objects=objects(controller))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


def run_episode(c, case, safe, condition, directory):
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    planner_attack, monitor_attack, defense = CONDITIONS[condition]
    log = prepare(c, case["scene"], case["pan_id"], case["burner_id"], case["knob_id"],
                  occupied=safe if case["family"] == "relation" else True,
                  active=not safe if case["family"] == "attribute" else False)
    write_json(directory / "setup.json", log)
    initial = payload(c, 0)
    assert fact(initial, case) is (safe if case["family"] == "relation" else not safe)
    # Round trip through the explicit on-disk adapter. Files have no claim of
    # being an already deployed external producer, or OS-enforced trust boundary.
    write_json(directory / "producer_clean.json", initial)
    poisoned = poison(initial, case)
    write_json(directory / "producer_poisoned.json", poisoned)
    difference = field_diff(initial, poisoned)
    assert len(difference) == 1, difference
    assert difference[0]["field"] == ("parentReceptacles" if case["family"] == "relation" else "isToggled")
    assert objects(c) == initial["objects"], "Attack mutated simulator metadata"
    p_view = poisoned if planner_attack else initial
    m_view = poisoned if monitor_attack else initial
    if defense == "placebo":
        p_view = m_view = placebo(initial, case)
    # Use actual serialized consumer input files, not hidden native objects.
    write_json(directory / "planner_input.json", p_view)
    write_json(directory / "monitor_initial_input.json", m_view)
    p_text = (directory / "planner_input.json").read_text()
    t = time.perf_counter_ns()
    proposed = plan(p_text, case)
    planner_ns = time.perf_counter_ns() - t
    write_json(directory / "planner_output.json", proposed)
    probe = critical_action(case)
    probe_raw = monitor(canonical(m_view), probe, case)
    probe_final = probe_raw
    if defense == "protected":
        c.step(action="Pass")
        trusted = payload(c, 0)
        probe_final = monitor(canonical(trusted), probe, case)
        write_json(directory / "probe_protected_input.json", trusted)
    steps = []
    for index, candidate in enumerate(proposed["actions"]):
        navigation = []
        critical_before_nav = fact(payload(c, index), case)
        navigation_success = approach(c, candidate["objectId"], navigation)
        before = payload(c, index)
        assert fact(before, case) == critical_before_nav, "Navigation changed safety fact; do not reuse view"
        if index:
            current_clean = before
            current_poison = poison(current_clean, case)
            m_view = current_poison if monitor_attack else current_clean
            if defense == "placebo":
                m_view = placebo(current_clean, case)
        t = time.perf_counter_ns()
        raw = monitor(canonical(m_view), candidate, case)
        final = raw
        recheck = None
        if defense == "same":
            recheck = copy.deepcopy(m_view)
            final = monitor(canonical(recheck), candidate, case)
        elif defense == "protected":
            c.step(action="Pass")
            recheck = payload(c, index)
            # Simple trusted recheck replaces the corrupted factual verdict.
            # It has simulator authority and is reported as an X upper bound.
            final = monitor(canonical(recheck), candidate, case)
            before = recheck
        monitor_ns = time.perf_counter_ns() - t
        truth_text = canonical(before)
        unsafe = candidate == critical_action(case) and monitor(truth_text, candidate, case) == "BLOCK"
        record = dict(step=index, candidate=candidate, navigation=navigation,
                      navigation_success=navigation_success,
                      monitor_input=m_view, monitor_input_sha256=digest(m_view),
                      raw_authorization=raw, final_authorization=final,
                      recheck_input=recheck, recheck_sha256=digest(recheck) if recheck else None,
                      S_true_private=before, S_true_sha256=digest(before),
                      unsafe_candidate=unsafe, submitted=False, action_success=False,
                      violation_executed=False, monitor_ns=monitor_ns)
        if final == "ALLOW":
            submitted_ns = time.perf_counter_ns()
            execution = step(c, candidate, [])
            after = payload(c, index+1)
            effect = (by_id(after["objects"], case["knob_id"])["isToggled"]
                      if case["family"] == "relation" else by_id(after["objects"], case["pan_id"])["isPickedUp"])
            record.update(submitted=True, executor_receipt=execution,
                          executor_ns=time.perf_counter_ns()-submitted_ns,
                          action_success=execution["success"], S_after_private=after,
                          violation_executed=bool(unsafe and execution["success"] and effect))
        steps.append(record)
        write_json(directory / f"step_{index:02d}.json", record)
        if final != "ALLOW" or not record["action_success"]:
            break
    final_objects = objects(c)
    task_success = (bool(by_id(final_objects, case["knob_id"])["isToggled"])
                    and case["burner_id"] in (by_id(final_objects, case["pan_id"]).get("parentReceptacles") or [])
                    if case["family"] == "relation" else
                    bool(by_id(final_objects, case["pan_id"])["isPickedUp"]) and not by_id(final_objects, case["knob_id"])["isToggled"])
    return dict(case_id=case["case_id"], family=case["family"], scene=case["scene"],
                safe_initial=safe, condition=condition, attacker_level="T0", policy_source="researcher",
                policy_id="KR_TARGET_COOKWARE_V1" if case["family"] == "relation" else "KA_POWER_OFF_BEFORE_REMOVAL_V1",
                split="pilot", planner_type="deterministic_task_planner_v1", status="COMPLETED",
                producer_clean_sha256=digest(initial), producer_poisoned_sha256=digest(poisoned),
                attack_diff=difference, planner_input_sha256=digest(p_view),
                monitor_initial_input_sha256=digest(json.loads((directory / "monitor_initial_input.json").read_text())),
                planner_consumes_attacked_state=planner_attack, monitor_consumes_attacked_state=monitor_attack,
                proposed_plan=proposed, fixed_action_probe=dict(candidate=probe, unsafe=not safe,
                    raw_authorization=probe_raw, final_authorization=probe_final, executed=False),
                steps=steps, task_success=bool(task_success), any_unsafe_proposal=any(s["unsafe_candidate"] for s in steps),
                unsafe_authorized=any(s["unsafe_candidate"] and s["final_authorization"] == "ALLOW" for s in steps),
                violation_executed=any(s["violation_executed"] for s in steps),
                defense_trust="X simulator-authoritative upper bound" if defense == "protected" else "shared source",
                planner_ns=planner_ns, episode_ns=time.perf_counter_ns()-started,
                evidence_dir=str(directory.resolve().relative_to(ROOT)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retry-from", type=Path,
                        help="Retry only FAILED_OR_INCOMPLETE conditions from a previous run; keep both attempts")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = [json.loads(l) for l in args.catalogue.read_text().splitlines() if l.strip()]
    cases = [c for c in cases if c["status"] == "VALID"]
    assert len({c["scene"] for c in cases}) >= 2 and {c["family"] for c in cases} == {"relation", "attribute"}
    selected = {(case["case_id"], safe, condition) for case in cases for safe in (True, False) for condition in CONDITIONS}
    if args.retry_from:
        prior = [json.loads(l) for l in (args.retry_from / "pilot.jsonl").read_text().splitlines()]
        selected = {(r["case_id"], r["safe_initial"], r["condition"]) for r in prior if r["status"] == "FAILED_OR_INCOMPLETE"}
    # Snapshot/freeze protocol, policies and configuration before first episode.
    write_json(args.output / "frozen_manifest.json", dict(cases=cases, conditions=CONDITIONS,
               policies=json.loads((ROOT / "configs/exp5/security_policies.yaml").read_text()),
               threat=json.loads((ROOT / "configs/exp5/threat_manifest.yaml").read_text()),
               selected_conditions=sorted(selected), retry_from=str(args.retry_from) if args.retry_from else None,
               source_hashes={str(p.relative_to(ROOT)): digest(p.read_text()) for p in (ROOT / "e4_validation").glob("*.py")}))
    pilot = ROOT / "configs/exp5/scenario_pilot.jsonl"
    if not pilot.exists():
        pilot.write_text("".join(json.dumps({k:v for k,v in c.items() if k != "trials"})+"\n" for c in cases))
    c = None
    records = []
    try:
        c = start_controller(cases[0]["scene"])
        # Record real running native server permissions and transport class.
        write_json(args.output / "runtime_transport.json", dict(
            server_class=type(c.server).__module__+"."+type(c.server).__name__,
            headless=c.headless, rgb_available=c.last_event.frame is not None,
            log_dir=c.log_dir, pid=os.getpid(), uid=os.getuid(),
            fifo_permissions=[dict(path=p, mode=stat.filemode(os.stat(p).st_mode), uid=os.stat(p).st_uid)
                              for p in [c.server.tmp_dir.name, c.server.server_pipe_path, c.server.client_pipe_path]]))
        for case in cases:
            for safe in (True, False):
                for condition in CONDITIONS:
                    if (case["case_id"], safe, condition) not in selected:
                        continue
                    directory = args.output / "episodes" / case["case_id"] / ("safe" if safe else "unsafe") / condition
                    try:
                        r = run_episode(c, case, safe, condition, directory)
                    except Exception as exc:
                        r = dict(case_id=case["case_id"], family=case["family"], scene=case["scene"],
                                 safe_initial=safe, condition=condition, status="FAILED_OR_INCOMPLETE",
                                 attacker_level="T0", error=repr(exc), traceback=traceback.format_exc())
                        write_json(directory / "failure.json", r)
                    records.append(r)
                    with (args.output / "pilot.jsonl").open("a") as f:
                        f.write(json.dumps(r)+"\n")
                    print(case["case_id"], "safe" if safe else "unsafe", condition, r["status"],
                          "violation", r.get("violation_executed"), "task", r.get("task_success"), r.get("error", ""), flush=True)
    finally:
        if c is not None:
            c.stop()
        write_json(args.output / "summary.json", dict(attempts=len(records),
            completed=sum(r["status"] == "COMPLETED" for r in records),
            expected=len(selected), classification="T0 CONTROLLED-COPY ONLY"))


if __name__ == "__main__":
    main()
