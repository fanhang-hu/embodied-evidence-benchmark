"""Read-only verification of a completed shadow run; no model/Unity/Monitor calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run, out = args.run.resolve(), args.out.resolve()
    if out.exists():
        raise SystemExit("Output already exists: " + str(out))
    files = [p for p in run.rglob("*") if p.is_file()]
    before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest = json.loads((run / "manifest.json").read_text())
    records = [json.loads(l) for l in (run / "records.jsonl").read_text().splitlines()]
    requests = [json.loads(l) for l in (run / "requests.jsonl").read_text().splitlines()]
    assert hashlib.sha256((run / "frozen_source.py").read_bytes()).hexdigest() == manifest["code_sha256"]
    assert hashlib.sha256(manifest["system_prompt"].encode()).hexdigest() == manifest["system_prompt_sha256"]
    # Evaluate with the exact archived version, without generating pycache files.
    import types
    frozen = types.ModuleType("e4_frozen_shadow_review")
    frozen.__file__ = str(run / "frozen_source.py")
    exec(compile((run / "frozen_source.py").read_text(), frozen.__file__, "exec"), frozen.__dict__)
    cases = [json.loads(l) for l in (root / "configs/exp5/scenario_pilot.jsonl").read_text().splitlines()]
    cases = {c["case_id"]:c for c in cases}
    assert len(records) == len(requests) == manifest["jobs"]
    by_job = {r["job_id"]:r for r in records}
    results = []
    for record, request in zip(records, requests):
        assert record["status"] == "OK", "Incomplete model response: " + str(record["job_id"])
        case = cases[record["case_id"]]
        source = root / record["source_input_path"]
        public = json.loads(source.read_text())
        truth = json.loads((source.parent / "producer_clean.json").read_text())
        assert frozen.sha(public) == record["source_state_sha256"]
        assert frozen.sha(truth) == record["private_evaluator_state_sha256"]
        prompt = frozen.build_prompt(public, case)
        assert prompt == record["prompt"] and frozen.sha(prompt) == record["prompt_sha256"]
        assert frozen.sha(request["request_body"]) == record["request_sha256"] == request["request_sha256"]
        assert request["request_body"]["messages"] == [
            dict(role="system", content=manifest["system_prompt"]), dict(role="user", content=frozen.canon(prompt))]
        assert record["finish_reason"] == "stop"
        expected = frozen.evaluate(record["raw_response"], prompt, public, truth, case)
        assert expected == record["evaluation"], "Evaluation mismatch: " + str(record["job_id"])
        assert not record["native_execution_tested"] and not record["monitor_authorization_tested"]
        if "response_reused_from_job" in record:
            original = by_job[record["response_reused_from_job"]]
            assert original["job_id"] < record["job_id"]
            assert original["request_sha256"] == record["request_sha256"]
            for key in ["raw_response", "usage", "returned_model", "provider_response_id"]:
                assert original[key] == record[key]
            assert not record["network_attempted"]
        results.append(dict(job_id=record["job_id"], family=record["family"],
                            safe_initial=record["safe_initial_private_eval_only"], condition=record["condition"],
                            actions=expected["actions"], unsafe_proposal=expected["unsafe_proposal_against_private_field_contract"],
                            private_precondition_errors=expected["private_true_state_evaluation"]["precondition_errors"],
                            response_reused_from_job=record.get("response_reused_from_job")))
    unique = [r for r in records if r["network_attempted"]]
    assert len(unique) == len({r["request_sha256"] for r in records}) == manifest["unique_requests"]
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p,h in before.items())
    report = dict(run=str(run.relative_to(root)), verification_pass=True,
                  requested_model=manifest["requested_model"], returned_models=sorted({r["returned_model"] for r in records}),
                  logical_jobs=len(records), successful_unique_provider_calls=len(unique),
                  reused_responses=len(records)-len(unique), records=results,
                  total_tokens_unique_calls=sum(r["usage"]["total_tokens"] for r in unique),
                  provider_latency_sec_sum_unique_calls=sum(r["latency_sec"] for r in unique),
                  native_execution_tested=False, monitor_authorization_tested=False,
                  input_artifact_sha256={str(p.relative_to(root)):h for p,h in before.items()},
                  original_run_artifacts_unchanged=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in {"input_artifact_sha256", "records"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
