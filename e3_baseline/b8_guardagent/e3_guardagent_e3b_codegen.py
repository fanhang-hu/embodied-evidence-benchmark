import _bootstrap  # Workspace paths and historical cross-script imports.
import os
import sys
import json
import time
from pathlib import Path

ROOT = Path("external/guardagent").resolve()
sys.path.insert(0, str(ROOT))

from openai import OpenAI
from guardagent import GuardAgent
from request_seeact import CodeGEN_Examples
from prompts_guard import GuardAgent_Message_Prompt
from utils import get_input_seeact, get_output_seeact

BASE = Path("results/E3/08_guardagent")
DATA = Path(
    "external/guardagent_dataset/seeact/sample_labeled_all.json"
)
PREVIOUS = BASE / "e3a_nonthinking.json"
OUT = BASE / "e3b_codegen.json"

key = os.environ.get("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY missing"

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
base_url = os.environ.get(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
)

assert base_url.startswith("https://")

data = json.loads(DATA.read_text())
previous = json.loads(PREVIOUS.read_text())

assert previous["status"] == "API_OUTPUT_PASS"
assert data[0]["annotation_id"] == previous["sample_annotation_id"]

sample = data[0]
agent_input, _, _, output_path = get_input_seeact(
    sample, output_dir=str(DATA.parent)
)
agent_output = get_output_seeact(output_path, 0)

# Reconstruct the official long-term memory using
# the parsing logic from GuardAgent main.py.
memory = []

for item in CodeGEN_Examples.split("\n\n"):
    item = item.split("Agent input:\n")[-1]
    agent_input_mem = item.split("\nAgent output:\n")[0]
    item = item.split("\nAgent output:\n")[-1]
    agent_output_mem = item.split("\nTask decomposition:\n")[0]
    item = item.split("\nTask decomposition:\n")[-1]
    subtasks = item.split("\nGuardrail code:\n")[0]
    code = item.split("\nGuardrail code:\n")[-1]

    memory.append({
        "agent input": agent_input_mem,
        "agent output": agent_output_mem,
        "subtasks": subtasks,
        "code": code,
    })

guard = GuardAgent(
    name="e3b_codegen_only",
    human_input_mode="NEVER",
    llm_config=False,
    code_execution_config=False,
    config_list=[],
)

guard.memory = memory
guard.num_shots = min(2, len(memory))

# Execute official example-retrieval method.
examples = guard.retrieve_examples(
    agent_input, agent_output
)

# Construct the original code-generation prompt.
prompt = GuardAgent_Message_Prompt.format(
    examples=examples,
    agent_input=agent_input,
    agent_output=agent_output,
    subtasks=previous["decomposition"],
)

print("=== GuardAgent E3B: Code Generation Only ===")
print("Model:", model)
print("Sample:", sample["annotation_id"])
print("Ground-truth label:", sample["label"])
print("Official memory entries:", len(memory))
print("Retrieved shots:", guard.num_shots)
print("Code-generation prompt chars:", len(prompt))

client = OpenAI(
    api_key=key,
    base_url=base_url,
    timeout=45,
    max_retries=0,
)

start = time.monotonic()

try:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a guardrail code generator. "
                    "Follow the supplied examples and "
                    "generate Python guardrail code only."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
        max_tokens=1800,
        extra_body={
            "thinking": {"type": "disabled"}
        },
    )

    choice = response.choices[0]
    generated = choice.message.content or ""
    elapsed = round(time.monotonic() - start, 3)

    print("Finish reason:", choice.finish_reason)
    print("Output chars:", len(generated))
    print("Elapsed seconds:", elapsed)

    print("\n=== Generated Code (NOT EXECUTED) ===")
    print(generated[:10000])

    passed = bool(
        generated.strip()
        and choice.finish_reason == "stop"
    )

    report = {
        "experiment": "GuardAgent-E3B",
        "status": (
            "CODE_OUTPUT_PASS"
            if passed else "REVIEW_REQUIRED"
        ),
        "model": model,
        "sample_annotation_id": sample["annotation_id"],
        "ground_truth_label": sample["label"],
        "memory_entries": len(memory),
        "retrieved_shots": guard.num_shots,
        "prompt_chars": len(prompt),
        "finish_reason": choice.finish_reason,
        "generated_code": generated,
        "elapsed_seconds": elapsed,
        "official_retrieval_used": True,
        "official_prompt_template_used": True,
        "official_codegen_orchestration_used": False,
        "api_adapter_used": True,
        "generated_code_executed": False,
        "full_guardagent_reproduced": False,
    }

except Exception as exc:
    report = {
        "experiment": "GuardAgent-E3B",
        "status": "API_ERROR",
        "error": f"{type(exc).__name__}: {exc}",
        "generated_code_executed": False,
    }
    print("API error:", report["error"])

finally:
    client.close()

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nGUARDAGENT-E3B", report["status"])
print("Saved:", OUT)

if report["status"] != "CODE_OUTPUT_PASS":
    sys.exit(1)
