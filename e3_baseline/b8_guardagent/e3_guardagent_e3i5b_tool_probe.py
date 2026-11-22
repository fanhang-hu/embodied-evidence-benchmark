import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import sys
from pathlib import Path

from openai import OpenAI

ROOT = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()
sys.path.insert(0, str(ROOT))

from config import model_config, llm_config_list

BASE = Path("results/E3/08_guardagent")
OUT = BASE / "e3i5b_tool_probe.json"

assert not OUT.exists(), f"Output exists: {OUT}"

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
cfg = model_config(model)

# Reuse the official GuardAgent function schema.
schema = llm_config_list(42, [cfg])["functions"][0]

client = OpenAI(
    api_key=cfg["api_key"],
    base_url=cfg["base_url"],
    timeout=60,
    max_retries=0,
)

response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": "Call the provided python tool. Do not write prose."
        },
        {
            "role": "user",
            "content": "Call python(cell) with code: print(1 + 1)"
        },
    ],
    tools=[
        {
            "type": "function",
            "function": schema,
        }
    ],
    tool_choice={
        "type": "function",
        "function": {"name": "python"},
    },
    temperature=0,
    max_tokens=160,
    extra_body={"thinking": {"type": "disabled"}},
)

choice = response.choices[0]
message = choice.message
calls = message.tool_calls or []

parsed_calls = []

for call in calls:
    args = json.loads(call.function.arguments)
    parsed_calls.append({
        "name": call.function.name,
        "arguments": args,
    })

passed = (
    len(parsed_calls) == 1
    and parsed_calls[0]["name"] == "python"
    and isinstance(
        parsed_calls[0]["arguments"].get("cell"), str
    )
    and bool(parsed_calls[0]["arguments"]["cell"].strip())
)

report = {
    "experiment": "GuardAgent-E3I-5B",
    "model": model,
    "protocol": "tools/tool_calls",
    "finish_reason": choice.finish_reason,
    "tool_calls": parsed_calls,
    "content": message.content,
    "pass": passed,
    "code_executed": False,
}

OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

print("Model:", model)
print("Finish reason:", choice.finish_reason)
print("Tool calls:", len(parsed_calls))
print("Function:", parsed_calls[0]["name"] if parsed_calls else None)
print("Arguments:", parsed_calls[0]["arguments"] if parsed_calls else None)
print("Saved:", OUT)
print("E3I-5B PASS" if passed else "E3I-5B NEEDS INSPECTION")
