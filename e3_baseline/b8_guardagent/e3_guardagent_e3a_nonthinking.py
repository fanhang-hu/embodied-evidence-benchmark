import _bootstrap  # Workspace paths and historical cross-script imports.
import os
import sys
import json
import time
import hashlib
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("external/guardagent").resolve()
sys.path.insert(0, str(ROOT))

from openai import OpenAI
import guardagent as guard_module
from guardagent import GuardAgent
from request_seeact import (
    User_Request_SeeAct,
    Specification_SeeAct,
    Decomposition_Examples,
)
from utils import get_input_seeact, get_output_seeact

DATA = Path(
    "external/guardagent_dataset/seeact/sample_labeled_all.json"
)
OUT = Path(
    "results/E3/08_guardagent/e3a_nonthinking.json"
)

key = os.environ.get("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY not set"

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
base_url = os.environ.get(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
)
assert base_url.startswith("https://")

data = json.loads(DATA.read_text(encoding="utf-8"))
assert len(data) == 200

sample = data[0]
agent_input, _, _, output_path = get_input_seeact(
    sample, output_dir=str(DATA.parent)
)
agent_output = get_output_seeact(output_path, 0)

print("=== GuardAgent E3A-Fix: Non-Thinking ===")
print("Model:", model)
print("Endpoint:", base_url)
print("Sample:", sample["annotation_id"])
print("Ground-truth label:", sample["label"])

# External API adapter.
# The official GuardAgent.task_decomposition() is unchanged.
client = OpenAI(
    api_key=key,
    base_url=base_url,
    timeout=30.0,
    max_retries=0,
)

api_records = []

class CompletionAdapter:
    def create(self, **kwargs):
        # Only adapt the model-specific thinking mode.
        # Keep official max_tokens=1000 and other parameters.
        kwargs["extra_body"] = {
            "thinking": {"type": "disabled"}
        }

        response = client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        record = {
            "finish_reason": choice.finish_reason,
            "content_chars": len(content),
            "prompt_tokens": (
                getattr(usage, "prompt_tokens", None)
                if usage else None
            ),
            "completion_tokens": (
                getattr(usage, "completion_tokens", None)
                if usage else None
            ),
            "max_tokens": kwargs["max_tokens"],
            "thinking_disabled": True,
        }

        api_records.append(record)

        print("API response metadata:")
        print(json.dumps(record, indent=2))

        return response

class ClientAdapter:
    def __init__(self):
        self.chat = SimpleNamespace(
            completions=CompletionAdapter()
        )

guard_module.OpenAI = lambda **kwargs: ClientAdapter()

guard = GuardAgent(
    name="e3a_nonthinking_guard",
    human_input_mode="NEVER",
    llm_config=False,
    code_execution_config=False,
    config_list=[],
)

start = time.monotonic()

decomposition = guard.task_decomposition(
    config={"model": model, "api_key": key},
    user_request=User_Request_SeeAct,
    agent_specification=Specification_SeeAct,
    agent_input=agent_input,
    agent_output=agent_output,
    Decomposition_Examples=Decomposition_Examples,
)

elapsed = round(time.monotonic() - start, 3)

success = bool(
    decomposition.strip()
    and not decomposition.startswith("Fail to retrieve")
)

print("\n=== Official Decomposition Output ===")
print(decomposition[:6000])
print("\nElapsed seconds:", elapsed)

report = {
    "experiment": "GuardAgent-E3A-Fix",
    "status": "API_OUTPUT_PASS" if success else "FAIL",
    "level": "official_decomposition_with_api_adapter",
    "model": model,
    "dataset_sha256": hashlib.sha256(
        DATA.read_bytes()
    ).hexdigest(),
    "sample_annotation_id": sample["annotation_id"],
    "ground_truth_label": sample["label"],
    "api_records": api_records,
    "decomposition": decomposition,
    "elapsed_seconds": elapsed,
    "original_method_used": True,
    "thinking_disabled": True,
    "original_max_tokens_preserved": True,
    "semantic_correctness_verified": False,
    "guardrail_code_executed": False,
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(
    "\nGUARDAGENT-E3A-FIX",
    report["status"]
)
print("Saved:", OUT)

client.close()

if not success:
    sys.exit(1)
