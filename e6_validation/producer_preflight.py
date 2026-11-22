"""Offline IPC / archive / policy matrix, explicitly without execution evidence."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path

from e4_validation.protocol import critical_action, digest, fact
from e5_validation.common import ROOT, file_sha, finish_hashes, state, write_json
from e5_validation.task_recovery_v2 import load_cache, lookup, unsafe
from e6_validation.producer_boundary import Producer
from e6_validation.producer_experiment import authorize, check_protocol, new_directory


class ReferenceDriver:
    """Counterfactual reference policy only. query() does NOT contact Unity."""
    def __init__(self, snapshot):
        self.truth, self.epoch = snapshot, 0
        self.queries = []

    def snapshot(self):
        return copy.deepcopy(self.truth)

    def query(self, reason):
        evidence = dict(payload=self.snapshot(), epoch=self.epoch,
                        query=dict(channel="offline_reference_only", reason=reason))
        self.queries.append(evidence)
        return evidence


def environment_check():
    result = dict(python_executable=os.path.realpath(os.sys.executable),
                  ai2thor_importable=importlib.util.find_spec("ai2thor") is not None,
                  Xvfb=shutil.which("Xvfb"), DISPLAY=os.environ.get("DISPLAY"))
    try:
        with tempfile.TemporaryDirectory(prefix="e6-socket-check-") as directory:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(Path(directory) / "probe.sock"))
        result["unix_socket_bind"] = True
    except OSError as exc:
        result.update(unix_socket_bind=False, socket_error=dict(errno=exc.errno, message=str(exc)))
    result["native_prerequisites_available"] = bool(
        result["ai2thor_importable"] and result["Xvfb"] and result["unix_socket_bind"])
    result["native_execution_tested"] = False
    return result


def probe(assignment, case, cache):
    safe = assignment["condition"] == "benign_safe"
    trials = [t for t in case["trials"] if t["expected_safe"] is safe]
    if len(trials) != 1:
        raise ValueError("Expected one archived physical reference per safety condition")
    truth = state(trials[0]["S_true"])
    mode = assignment["pollution_mode"] if assignment["condition"] == "producer_attack" else "clean"
    with Producer(case, mode=mode, persistence=assignment["persistence"]) as producer:
        planner_input, planner_publication = producer.publish(truth)
        plan = lookup(planner_input, case, cache)
        candidate = critical_action(case)
        if candidate not in plan["actions"]:
            raise ValueError("Archived plan does not contain the critical candidate")
        public, publication = producer.publish(truth)
        driver = ReferenceDriver(truth)
        cache_ref = driver.query("offline_initial_cache") if assignment["arm"] in {
            "receipt_invalidation", "source_aware_hybrid"} else None
        decision, _, evidence = authorize(driver, producer, assignment["arm"], public,
                                          publication, candidate, case, cache_ref)
        return dict(assignment, status="OFFLINE_PROBE_COMPLETE", stage="archived_candidate_policy_probe",
                    boundary=producer.boundary, true_fact=fact(truth, case),
                    planner_fact=fact(planner_input, case), candidate=candidate,
                    unsafe_candidate=unsafe(candidate, truth, case),
                    planner_input_sha256=digest(planner_input),
                    archived_request_sha256=plan["request_sha256"],
                    archived_prompt_sha256=plan["prompt_sha256"],
                    planner_publication=planner_publication, publications=producer.publications,
                    authorization=decision, evidence_channel=evidence["channel"],
                    evidence_fact=fact(evidence["payload"], case) if evidence["payload"] else None,
                    reference_queries=len(driver.queries), actual_protected_queries=0,
                    native_execution_tested=False, execution_ASR=None,
                    safe_task_success=None, online_llm_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    path = Path(args.protocol).resolve()
    protocol = check_protocol(path)
    cases = {c["case_id"]: c for c in protocol["cases"]}
    cache = load_cache()
    out = new_directory(args.out)
    rows = []
    for assignment in protocol["assignments"]:
        try:
            row = probe(assignment, cases[assignment["case_id"]], cache)
        except Exception as exc:
            row = dict(assignment, status="FAILED", error=repr(exc))
        rows.append(row)
    import collections
    counts = collections.Counter(r["status"] for r in rows)
    write_json(out / "preflight.json", dict(
        schema="e6.offline_producer_preflight.v2", protocol=str(path.relative_to(ROOT)),
        protocol_sha256=file_sha(path), rows=rows, expected=protocol["expected"],
        status="PASS" if len(rows) == protocol["expected"] and counts["FAILED"] == 0 else "FAIL",
        status_counts=dict(counts), native_environment=environment_check(),
        native_Unity_calls=0, online_llm_calls=0,
        limitations=["Fixed critical-candidate probes from archived snapshots; no plan prefix was executed",
                     "Reference fresh queries read an offline snapshot, not a real protected sensor",
                     "Receipt intervals and native execution require the separately frozen native matrix",
                     "No execution ASR, task success, deployment exploit or E6 completion claim"],
    ))
    finish_hashes(out)
    print(dict(counts), flush=True)
    print(out / "preflight.json")
    if counts["FAILED"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
