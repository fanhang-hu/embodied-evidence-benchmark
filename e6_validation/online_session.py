"""Durable one-request-per-assignment ledger. Interrupted requests are never retried."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from e4_validation.llm_shadow import build_prompt, invoke, make_request, sha
from e4_validation.protocol import digest
from e5_validation.common import file_sha, read_json
from e6_validation.online_planner import OnlinePlanner, parse_actions


def durable_json(path, value, *, replace=False, lines=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for item in value if lines else [value]:
                json.dump(item, handle, ensure_ascii=False, allow_nan=False, indent=None if lines else 2)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # Atomic publish; refuse an existing record.
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def provider_config():
    # Reuse HTTPS/key validation without making any request or writing a file.
    planner = OnlinePlanner(Path("."), max_calls=1)
    return {k: getattr(planner.args, k) for k in
            ("base_url", "model", "timeout", "max_tokens", "api_key_env")}


def error_record(exc):
    # Store diagnostic codes, never arbitrary exception text/headers/credentials.
    reason = getattr(exc, "reason", exc)
    return dict(type=type(exc).__name__, errno=getattr(reason, "errno", None),
                http_status=getattr(exc, "code", None))


class JournalPlanner:
    def __init__(self, out, protocol, protocol_sha256):
        self.out, self.protocol, self.protocol_sha256 = Path(out), protocol, protocol_sha256
        self.args = SimpleNamespace(**protocol["provider_config"])
        if protocol["online_call_budget"] != protocol["expected"] or not 1 <= protocol["expected"] <= 24:
            raise ValueError("One reserved call per frozen assignment, maximum 24")

    def request_path(self, index):
        return self.out / f"call_{index:03d}.request.json"

    def result_path(self, index):
        return self.out / f"call_{index:03d}.json"

    def provide_for(self, index, public, case):
        if not 0 <= index < self.protocol["expected"]:
            raise ValueError("Call index outside the frozen budget")
        assignment = self.protocol["assignments"][index]
        expected_case = next(c for c in self.protocol["cases"] if c["case_id"] == assignment["case_id"])
        if case != expected_case:
            raise ValueError("Call case does not match its frozen assignment")
        path = self.request_path(index)
        if path.exists() or self.result_path(index).exists():
            raise ValueError("Call slot already reserved; no retry or response replay")
        if not os.environ.get(self.args.api_key_env):
            raise RuntimeError("Configured API credential missing")
        prompt = build_prompt(public, case)
        body = make_request(prompt, self.args)
        record = dict(call_index=index, episode_index=index, mode="online_actual_request",
                      protocol_sha256=self.protocol_sha256, assignment=assignment,
                      request_body=body, request_sha256=sha(body), prompt_sha256=sha(prompt),
                      public_state_sha256=digest(public), request_ns=time.perf_counter_ns())
        durable_json(path, dict(record, status="REQUEST_STARTED"))
        record["reservation_sha256"] = file_sha(path)
        phase = "request"
        try:
            response = invoke(body, self.args)
            record.update(response=response, response_ns=time.perf_counter_ns())
            phase = "response_validation"
            actions = parse_actions(response, prompt)
        except Exception as exc:
            durable_json(self.result_path(index), dict(record, status="FAILED", failure_phase=phase,
                                                       error=error_record(exc), failure_ns=time.perf_counter_ns()))
            raise
        durable_json(self.result_path(index), dict(record, status="OK"))
        return dict(prompt=prompt, raw_actions=copy.deepcopy(actions),
                    actions=[dict(a, forceAction=False) for a in actions], mode="online_actual_request",
                    request_sha256=record["request_sha256"], prompt_sha256=record["prompt_sha256"],
                    public_state_sha256=digest(public), call_index=index,
                    call_record=str(self.result_path(index)), response=response,
                    planner_latency_ns=record["response_ns"]-record["request_ns"])

    def inventory(self):
        records = {}
        for path in sorted(self.out.glob("call_*.request.json")):
            request = read_json(path)
            index = request["call_index"]
            if (not 0 <= index < self.protocol["expected"] or path != self.request_path(index)
                    or request["episode_index"] != index or request["protocol_sha256"] != self.protocol_sha256
                    or request["assignment"] != self.protocol["assignments"][index]
                    or request["request_sha256"] != sha(request["request_body"])
                    or request["status"] != "REQUEST_STARTED"):
                raise ValueError("Call reservation identity mismatch")
            terminal_path = self.result_path(index)
            prompt = json.loads(request["request_body"]["messages"][1]["content"])
            if (request["request_body"] != make_request(prompt, self.args)
                    or request["prompt_sha256"] != sha(prompt)):
                raise ValueError("Reserved request differs from frozen provider configuration")
            terminal = read_json(terminal_path) if terminal_path.exists() else None
            if terminal is not None:
                if (terminal["status"] not in {"OK", "FAILED"}
                        or terminal["reservation_sha256"] != file_sha(path)
                        or any(terminal[k] != v for k, v in request.items() if k != "status")):
                    raise ValueError("Call response is not bound to its reservation")
            records[index] = dict(request=request, terminal=terminal)
        expected_files = {self.request_path(i) for i in records} | {
            self.result_path(i) for i in records if records[i]["terminal"] is not None}
        if set(self.out.glob("call_*.json")) != expected_files:
            raise ValueError("Orphan or unrecognized call record")
        return records
