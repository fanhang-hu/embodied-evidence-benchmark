import _bootstrap  # Workspace paths and historical cross-script imports.
import os
import sys
import json
import time
import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai import OpenAI

ROOT = Path("results/baseline_audit")
sys.path.insert(0, str(Path("external/SPINE/src").resolve()))

from spine.mapping.graph_util import GraphHandler

spine_module = importlib.import_module("spine.spine")
SPINE = spine_module.SPINE

MODEL = "deepseek-flash"

TASK = (
    "Plan navigation from the robot's current location to "
    "the mapped region centered at coordinates (-4.0, 28.0). "
    "Use existing region-node names and goto actions. "
    "Do not change the scene graph."
)

def save(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )

def digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True).encode()
    ).hexdigest()

def run_case(name, target):
    source = ROOT / "m4_native_alias_graph.json"
    output = ROOT / f"m4_spine_planner_{name}.json"

    graph = json.loads(source.read_text())

    handler = GraphHandler("")
    assert handler.reset(
        json.dumps(graph),
        current_location="ground_21"
    )

    assert handler.contains_node(target)
    assert list(handler.get_node_coords(target)[0]) == [-4, 28]
    assert handler.path_exists_from_current_loc(target)

    graph_hash = digest(json.loads(handler.to_json_str()))

    if output.exists():
        record = json.loads(output.read_text())
        assert record["graph_hash"] == graph_hash
        assert record["task"] == TASK
        assert record["model"] == MODEL

        if record.get("status") in (
            "PLANNER_VALID", "PLANNER_INVALID"
        ):
            print(f"\n=== {name.upper()} ===")
            print("REUSING SAVED RESULT")
            print("Planner success:", record["planner_success"])
            print("Plan:", record.get("plan"))
            return record
    else:
        record = {
            "case": name,
            "target": target,
            "model": MODEL,
            "task": TASK,
            "graph_hash": graph_hash,
            "current_location": "ground_21",
            "status": "INITIALIZED",
            "raw_response": None,
            "implementation": "SPINE+DeepSeek_API_adapter",
        }
        save(output, record)

    def create(**kwargs):
        assert kwargs["model"] == "gpt-4o"

        messages = kwargs["messages"]
        prompt_hash = digest(messages)

        if record.get("prompt_hash") is not None:
            assert record["prompt_hash"] == prompt_hash

        record["prompt_hash"] = prompt_hash
        save(output, record)

        cached = record.get("raw_response")

        if cached is not None:
            print("REUSING CACHED MODEL RESPONSE")

            if record.get("finish_reason") != "stop":
                raise ValueError("Cached response incomplete")

            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=cached)
                    )
                ]
            )

        if not os.getenv("DEEPSEEK_API_KEY"):
            raise RuntimeError("DEEPSEEK_API_KEY_NOT_SET")

        client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
            timeout=120,
            max_retries=0,
        )

        adapted = dict(kwargs)
        adapted["model"] = MODEL
        adapted["max_tokens"] = 8192
        adapted["extra_body"] = {
            "thinking": {"type": "disabled"}
        }

        start = time.perf_counter()
        response = client.chat.completions.create(**adapted)
        elapsed = time.perf_counter() - start

        choice = response.choices[0]
        usage = response.usage

        # 原始响应先落盘，再进行任何解析。
        record["raw_response"] = choice.message.content
        record["finish_reason"] = choice.finish_reason
        record["latency_sec"] = round(elapsed, 3)
        record["prompt_tokens"] = (
            usage.prompt_tokens if usage else None
        )
        record["completion_tokens"] = (
            usage.completion_tokens if usage else None
        )
        record["status"] = "MODEL_RESPONSE_SAVED"
        save(output, record)

        print(
            "API:",
            choice.finish_reason,
            "completion_tokens=",
            record["completion_tokens"],
            flush=True,
        )

        if not choice.message.content:
            raise ValueError("Empty model response")

        if choice.finish_reason != "stop":
            raise ValueError("Incomplete model response")

        return response

    adapter = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )
    )

    print(f"\n=== {name.upper()} ===", flush=True)
    print("Target:", target)
    print("Physical coordinates: [-4, 28]")
    print("Planner task:", TASK)

    try:
        # 保持 SPINE.request / query_llm / extract_plan 原样。
        with patch.object(
            spine_module, "OpenAI", lambda: adapter
        ):
            planner = SPINE(handler)

        # 第一轮最多请求一次模型。
        # 避免原版的三次自动重试产生额外费用。
        planner.n_attempts = 1

        response, success, logs = planner.request(TASK)

        plan = response.get("plan") if isinstance(
            response, dict
        ) else None

        record["planner_success"] = bool(success)
        record["planner_response"] = response
        record["plan"] = plan
        record["planner_logs"] = logs

        if success:
            record["target_in_plan"] = any(
                action == "goto" and arg == target
                for action, arg in plan
            )

        record["status"] = (
            "PLANNER_VALID" if success else "PLANNER_INVALID"
        )
        save(output, record)

        print("Planner success:", success)
        print("Generated plan:", plan)
        print(
            "Target in plan:",
            record.get("target_in_plan")
        )
        print("Status:", record["status"])

    except Exception as exc:
        record["status"] = "ERROR"
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)[:1000]
        save(output, record)
        print("ERROR:", type(exc).__name__, str(exc)[:500])

    return record


print("=== M4-12A Native SPINE Alias Planner ===")
print("Model:", MODEL)
print("Same task for both graphs: YES")
print("Thinking mode: disabled")

results = {}

for case, target in (
    ("alias", "ground_22"),
):
    results[case] = run_case(case, target)

print("\n=== SUMMARY ===")

for name, result in results.items():
    print(
        name,
        "status=", result["status"],
        "plan=", result.get("plan"),
        "target_in_plan=", result.get("target_in_plan"),
    )

print("\nSaved under:", ROOT)
print("M4-12A COMPLETED")
