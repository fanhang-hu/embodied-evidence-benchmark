import _bootstrap  # Workspace paths and historical cross-script imports.
import os
import sys
import json
import time
import hashlib
from pathlib import Path

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
OUT = Path("results/E3/08_guardagent/e3a_task_decomposition.json")

key = os.environ.get("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY is not set"

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
base_url = os.environ.get(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com/v1",
)

assert base_url.startswith("https://"), \
    "Use an HTTPS API endpoint"

print("=== GuardAgent E3A: Official Task Decomposition ===")
print("Model:", model)
print("API endpoint:", base_url)
print("API key available: True (value hidden)")

data = json.loads(DATA.read_text())
assert len(data) == 200

sample = data[0]

# Use exactly the original SeeAct input extraction functions.
agent_input, _, _, output_path = get_input_seeact(
    sample,
    output_dir=str(DATA.parent),
)
agent_output = get_output_seeact(output_path, 0)

print("Dataset SHA256:",
      hashlib.sha256(DATA.read_bytes()).hexdigest())
print("Sample annotation ID:", sample["annotation_id"])
print("Ground-truth label:", sample["label"])

# Only adapt the transport endpoint. Keep official method unchanged.
guard_module.OpenAI = lambda **kwargs: OpenAI(
    api_key=kwargs["api_key"],
    base_url=base_url,
    timeout=25.0,
    max_retries=0,
)

guard = GuardAgent(
    name="e3a_decomposition_only",
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

failure = (
    not decomposition.strip()
    or decomposition.startswith("Fail to retrieve")
)

print("\n=== Model Output ===")
print(decomposition[:6000])
print("\nElapsed seconds:", elapsed)

report = {
    "experiment": "GuardAgent-E3A",
    "status": "PASS" if not failure else "FAIL",
    "level": "official_task_decomposition_with_api_adapter",
    "dataset_sha256": hashlib.sha256(
        DATA.read_bytes()
    ).hexdigest(),
    "sample_annotation_id": sample["annotation_id"],
    "ground_truth_label": sample["label"],
    "model": model,
    "api_base_url": base_url,
    "decomposition": decomposition,
    "elapsed_seconds": elapsed,
    "official_method_executed": True,
    "original_gpt4_used": False,
    "code_generated_or_executed": False,
    "full_guardagent_executed": False,
    "semantic_correctness_manually_verified": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nGUARDAGENT-E3A", report["status"])
print("Saved:", OUT)

if failure:
    sys.exit(1)
