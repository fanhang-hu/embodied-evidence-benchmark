import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import sys
from pathlib import Path

from autogen import AssistantAgent

ROOT = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()
sys.path.insert(0, str(ROOT))

from config import model_config, llm_config_list

BASE = Path("results/E3/08_guardagent")
OUT = BASE / "e3i5_codegen.json"

assert not OUT.exists(), f"Output already exists: {OUT}"

# Load the prompt built through the official GuardAgent class.
previous = json.loads(
    (BASE / "e3i4_prompt.json").read_text()
)
prompt = previous["prompt"]

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
cfg = model_config(model)

# Reuse official AutoGen function-call specification.
llm_config = llm_config_list(42, [cfg])
llm_config["cache_seed"] = None

chatbot = AssistantAgent(
    name="chatbot",
    system_message=(
        "For coding tasks, only use the functions "
        "you have been provided with. "
        "Reply TERMINATE when the task is done."
    ),
    llm_config=llm_config,
)

print("=== GuardAgent E3I-5 ===", flush=True)
print("Model:", model, flush=True)
print("Prompt chars:", len(prompt), flush=True)
print("Function interface: python(cell)", flush=True)

# Generate one reply only. No function executor is connected.
reply = chatbot.generate_reply(
    messages=[
        {"role": "user", "content": prompt}
    ]
)

print("Reply type:", type(reply).__name__, flush=True)

function_call = None
content = None

if isinstance(reply, dict):
    function_call = reply.get("function_call")
    content = reply.get("content")
else:
    content = reply

generated_code = None

if isinstance(function_call, dict):
    args = function_call.get("arguments", "")

    try:
        parsed = json.loads(args) if isinstance(args, str) else args
        generated_code = parsed.get("cell")
    except (json.JSONDecodeError, AttributeError):
        pass

report = {
    "experiment": "GuardAgent-E3I-5",
    "implementation": "official_autogen_function_interface",
    "model": model,
    "sample_annotation_id": previous["sample_annotation_id"],
    "prompt_source": "e3i4_prompt.json",
    "reply_type": type(reply).__name__,
    "function_name": (
        function_call.get("name")
        if isinstance(function_call, dict)
        else None
    ),
    "function_call": function_call,
    "content": content,
    "generated_code": generated_code,
    "code_generated": bool(generated_code),
    "code_executed": False,
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("Function:", report["function_name"], flush=True)
print("Code generated:", report["code_generated"], flush=True)
print(
    "Code chars:",
    len(generated_code or ""),
    flush=True
)
print("Saved:", OUT, flush=True)

if report["function_name"] == "python" and generated_code:
    print("E3I-5 PASS: Function call generated")
else:
    print("E3I-5 NEEDS INSPECTION")
