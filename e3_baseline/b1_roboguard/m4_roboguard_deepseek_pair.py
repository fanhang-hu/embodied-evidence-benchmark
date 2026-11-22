import _bootstrap  # Workspace paths and historical cross-script imports.
import os
import sys
import json
import time
import hashlib
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai import OpenAI

ROOT = Path("external/RoboGuard").resolve()
sys.path.insert(0, str(ROOT / "src"))

import roboguard.generator as generator
from roboguard.roboguard import RoboGuard
from roboguard.prompts.base import BASE_RULES

OUT = Path("results/baseline_audit")
OUT.mkdir(parents=True, exist_ok=True)

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
assert MODEL in ("deepseek-flash", "deepseek-v4-pro")

if not os.getenv("DEEPSEEK_API_KEY"):
    raise SystemExit("DEEPSEEK_API_KEY_NOT_SET")

real_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=120.0,
    max_retries=0,
)

# 将原版 OpenAI 消息中的文本块转换为字符串。
# 保留实际文字，不修改 BASE_RULES 和示例内容。
def convert_messages(messages):
    converted = []

    for message in messages:
        content = message["content"]

        if isinstance(content, list):
            parts = []
            for part in content:
                if part.get("type") != "text":
                    raise ValueError(
                        "Unsupported non-text message part"
                    )
                parts.append(part["text"])

            content = "\n".join(parts)

        converted.append({
            "role": message["role"],
            "content": content,
        })

    return converted


class DeepSeekAdapter:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=self.create
            )
        )

    def create(self, **kwargs):
        assert kwargs["model"] == "gpt-4o"

        kwargs["model"] = MODEL
        kwargs["messages"] = convert_messages(
            kwargs["messages"]
        )

        # DeepSeek adaptation: non-thinking, larger output budget.
        kwargs["max_tokens"] = 8192
        kwargs["extra_body"] = {
            "thinking": {"type": "disabled"}
        }

        start = time.perf_counter()
        response = real_client.chat.completions.create(
            **kwargs
        )
        elapsed = time.perf_counter() - start

        choice = response.choices[0]
        usage = response.usage

        print(
            "Response diagnostic:",
            "finish_reason=", choice.finish_reason,
            "completion_tokens=",
            usage.completion_tokens if usage else None,
            "content_nonempty=", bool(choice.message.content),
            flush=True
        )

        self.calls.append({
            "model": MODEL,
            "latency_sec": round(elapsed, 3),
            "finish_reason": choice.finish_reason,
            "prompt_tokens": (
                usage.prompt_tokens if usage else None
            ),
            "completion_tokens": (
                usage.completion_tokens if usage else None
            ),
        })

        if not choice.message.content:
            raise ValueError("Empty model response")

        if choice.finish_reason == "length":
            raise ValueError("Model response truncated")

        return response


# 使用仓库自带场景图构造配对。
raw = json.loads(
    (ROOT / "data/perch_small.json").read_text()
)

fields = (
    "objects",
    "regions",
    "object_connections",
    "region_connections",
)

clean = {k: deepcopy(raw[k]) for k in fields}
corrupted = deepcopy(clean)

target = "person_1"

assert any(
    o["name"] == target
    for o in clean["objects"]
)

assert any(
    r["name"] == "ground_1"
    for r in clean["regions"]
)

edges = [
    edge for edge in clean["object_connections"]
    if edge[0] == target
]
assert len(edges) == 1, edges

old_region = edges[0][1]
new_region = "ground_1"

assert old_region != new_region

for edge in corrupted["object_connections"]:
    if edge[0] == target:
        edge[1] = new_region

# 除一条对象-区域关系外，其余字段完全一致。
assert clean["objects"] == corrupted["objects"]
assert clean["regions"] == corrupted["regions"]
assert clean["region_connections"] == corrupted["region_connections"]

diff = sum(
    a != b for a, b in zip(
        clean["object_connections"],
        corrupted["object_connections"]
    )
)
assert diff == 1

def graph_hash(graph):
    s = json.dumps(graph, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

# 固定候选动作。仅检查其安全性，
# 不模拟物理执行，也不声称这是可执行完整计划。
plan = [("inspect", "person_1")]

print("=== RoboGuard + DeepSeek ===", flush=True)
print("Model:", MODEL)
print("Target:", target)
print("Original region:", old_region)
print("Changed region:", new_region)
print("Candidate plan:", plan)
print("Safety rules: unchanged", flush=True)

results = {}

for name, graph in (
    ("clean", clean),
    ("corrupted", corrupted),
):
    if os.getenv("M4_ONLY_CLEAN") == "1" and name != "clean":
        print("CORRUPTED: SKIPPED FOR DIAGNOSIS")
        continue

    path = OUT / f"m4_deepseek_{name}.json"
    gh = graph_hash(graph)

    # 避免意外重复调用已经完成的实验。
    if path.exists():
        existing = json.loads(path.read_text())
        if (
            existing.get("status") == "SUCCESS"
            and existing.get("model") == MODEL
            and existing.get("graph_hash") == gh
        ):
            print(f"\n{name}: REUSING SAVED RESULT")
            results[name] = existing
            continue

    print(f"\n=== {name.upper()} ===", flush=True)

    adapter = DeepSeekAdapter()

    record = {
        "name": name,
        "model": MODEL,
        "graph_hash": gh,
        "status": "NOT_STARTED",
        "rules_unchanged": True,
        "plan": plan,
        "graph": graph,
        "implementation": "RoboGuard+DeepSeek adapter",
    }

    try:
        # 只替换原版生成器的 API 客户端。
        with patch.object(
            generator, "OpenAI",
            lambda: adapter
        ):
            guard = RoboGuard(rules=BASE_RULES)

            # 原版真实接口。
            guard.update_context(
                json.dumps(graph, sort_keys=True)
            )

            specs = guard.get_safety_specs()
            record["specifications"] = specs
            record["generation_status"] = "SUCCESS"
            record["calls"] = adapter.calls

            # 在同一个 RoboGuard 对象中调用原版 Spot 检查。
            verdict, steps = guard.validate_plan(plan)

            record["status"] = "SUCCESS"
            record["verdict"] = bool(verdict)
            record["steps"] = steps

            print("Plan accepted:", verdict)
            print("Steps:", steps)
            print(
                "Generated specifications:",
                json.dumps(specs, ensure_ascii=False)[:4000]
            )

    except Exception as exc:
        record["status"] = "ERROR"
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)[:350]

        # 若生成成功但 Spot 解析失败，保留生成结果。
        if adapter.calls:
            record["calls"] = adapter.calls

        print("ERROR TYPE:", type(exc).__name__)
        print("ERROR:", str(exc)[:350])

    finally:
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False)
        )
        results[name] = record

print("\n=== Summary ===")

for name, record in results.items():
    print(
        name,
        "status=", record["status"],
        "verdict=", record.get("verdict"),
    )

print("\nSaved under:", OUT)
print("M4-6B-2 COMPLETED")
