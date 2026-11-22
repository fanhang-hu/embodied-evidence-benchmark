import _bootstrap  # Workspace paths and historical cross-script imports.
import hashlib
import json
import os
import sys
from pathlib import Path

from openai import OpenAI

ROOT = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()
sys.path.insert(0, str(ROOT))

from config import model_config, llm_config_list

BASE = Path("results/E3/08_guardagent")
OUT = BASE / "e3i5d_real_toolcall.json"

assert not OUT.exists(), f"Output exists: {OUT}"

previous = json.loads(
    (BASE / "e3i4_prompt.json").read_text()
)

prompt = previous["prompt"]
assert len(prompt) > 10000

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
cfg = model_config(model)

schema = llm_config_list(42, [cfg])["functions"][0]

client = OpenAI(
    api_key=cfg["api_key"],
    base_url=cfg["base_url"],
    timeout=90,
    max_retries=0,
)

print("=== GuardAgent E3I-5D ===", flush=True)
print("Model:", model, flush=True)
print("Prompt chars:", len(prompt), flush=True)
print("Tool: python(cell)", flush=True)

try:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "For coding tasks, only use the functions "
                    "you have been provided with. "
                    "Reply TERMINATE when the task is done."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        tools=[
            {
                "type": "function",
                "function": schema,
            }
        ],
        tool_choice="auto",
        temperature=0,
        max_tokens=2500,
        extra_body={"thinking": {"type": "disabled"}},
    )
finally:
    client.close()

choice = response.choices[0]
message = choice.message

calls = []

for call in message.tool_calls or []:
    raw_args = call.function.arguments
    try:
        args = json.loads(raw_args)
        parse_error = None
    except (json.JSONDecodeError, TypeError) as exc:
        args = None
        parse_error = str(exc)

    calls.append({
        "id": call.id,
        "name": call.function.name,
        "raw_arguments": raw_args,
        "arguments": args,
        "parse_error": parse_error,
    })

valid = (
    len(calls) == 1
    and calls[0]["name"] == "python"
    and isinstance(calls[0]["arguments"], dict)
    and isinstance(calls[0]["arguments"].get("cell"), str)
    and bool(calls[0]["arguments"]["cell"].strip())
)

report = {
    "experiment": "GuardAgent-E3I-5D",
    "implementation": "deepseek_tools_adapter",
    "model": model,
    "sample_annotation_id": previous["sample_annotation_id"],
    "prompt_source": "e3i4_prompt.json",
    "prompt_sha256": hashlib.sha256(
        prompt.encode()
    ).hexdigest(),
    "tool_choice": "auto",
    "finish_reason": choice.finish_reason,
    "content": message.content,
    "tool_calls": calls,
    "valid_python_tool_call": valid,
    "code_executed": False,
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("Finish reason:", choice.finish_reason)
print("Tool calls:", len(calls))
print("Valid python(cell):", valid)

if valid:
    cell = calls[0]["arguments"]["cell"]
    print("Generated code chars:", len(cell))
    print("E3I-5D PASS")
else:
    print("Response preview:", repr(message.content)[:500])
    print("E3I-5D NEEDS INSPECTION")

print("Saved:", OUT)
