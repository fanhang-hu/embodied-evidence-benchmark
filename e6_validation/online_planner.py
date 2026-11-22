"""Bounded live planning on Producer-visible evidence. No archive fallback."""
from __future__ import annotations

import argparse
import copy
import os
import time
import urllib.parse
from types import SimpleNamespace

from e4_validation.llm_shadow import build_prompt, extract_json, invoke, make_request, sha
from e4_validation.protocol import digest
from e5_validation.common import finish_hashes, read_json, write_json
from e6_validation.producer_experiment import new_directory


def parse_actions(response, prompt):
    if response.get("finish_reason") != "stop":
        raise ValueError("Online response did not finish normally")
    parsed = extract_json(response["raw_response"])
    if not isinstance(parsed, dict) or set(parsed) != {"actions"} or not isinstance(parsed["actions"], list):
        raise ValueError("Expected exactly JSON.actions")
    actions = parsed["actions"]
    if len(actions) > 16:
        raise ValueError("Online plan exceeds action budget")
    for action in actions:
        if (not isinstance(action, dict) or set(action) != {"action", "objectId"}
                or action not in prompt["allowed_actions"]):
            raise ValueError("Online action outside the frozen action/target whitelist")
    return actions


class OnlinePlanner:
    def __init__(self, out, *, max_calls=12, timeout=40, max_tokens=800):
        if max_calls < 1 or max_calls > 24 or not 1 <= timeout <= 45:
            raise ValueError("Expected 1..24 calls and a 1..45 second timeout")
        base = os.environ.get("E4_LLM_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        parsed = urllib.parse.urlsplit(base)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("Online endpoint must be HTTPS without embedded credentials/query")
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise RuntimeError("DEEPSEEK_API_KEY not configured")
        self.args = SimpleNamespace(base_url=base, model=os.environ.get("E4_LLM_MODEL")
                                    or os.environ.get("DEEPSEEK_MODEL") or "deepseek-flash",
                                    timeout=timeout, max_tokens=max_tokens, api_key_env="DEEPSEEK_API_KEY")
        self.out, self.max_calls, self.calls = out, max_calls, 0

    def provide(self, public, case):
        if self.calls >= self.max_calls:
            raise RuntimeError("Online call budget exhausted")
        index = self.calls
        self.calls += 1
        prompt = build_prompt(public, case)
        request = make_request(prompt, self.args)
        record = dict(call_index=index, mode="online_actual_request", request_body=request,
                      request_sha256=sha(request), prompt_sha256=sha(prompt),
                      public_state_sha256=digest(public), request_ns=time.perf_counter_ns())
        path = self.out / f"call_{index:03d}.json"
        write_json(path, dict(record, status="REQUEST_STARTED"))
        try:
            response = invoke(request, self.args)
            record.update(response=response, response_ns=time.perf_counter_ns())
            actions = parse_actions(response, prompt)
        except Exception as exc:
            # Exception class/message does not include headers or API keys.
            record.update(status="FAILED", error=type(exc).__name__ + ": " + str(exc),
                          failure_ns=time.perf_counter_ns())
            write_json(path, record)
            raise
        record["status"] = "OK"
        write_json(path, record)
        return dict(prompt=prompt, raw_actions=copy.deepcopy(actions),
                    actions=[dict(a, forceAction=False) for a in actions],
                    mode="online_actual_request", request_sha256=record["request_sha256"],
                    prompt_sha256=record["prompt_sha256"], public_state_sha256=digest(public),
                    call_index=index, call_record=str(path), response=response,
                    planner_latency_ns=record["response_ns"]-record["request_ns"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-episode", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source = read_json(args.source_episode)
    out = new_directory(args.out)
    result = dict(stage="online_planning_only", native_execution_tested=False,
                  execution_ASR=None, safe_task_success=None, source_episode=args.source_episode)
    try:
        planner = OnlinePlanner(out, max_calls=1)
        plan = planner.provide(source["planner_input"], source["case"])
        result.update(status="OK", online_calls=planner.calls, plan=plan)
    except Exception as exc:
        result.update(status="FAILED", error=type(exc).__name__ + ": " + str(exc))
    write_json(out / "summary.json", result)
    finish_hashes(out)
    print({k: v for k, v in result.items() if k not in {"plan"}})
    if result["status"] != "OK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
