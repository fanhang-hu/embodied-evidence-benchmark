import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path

ROOT = Path("external/guardagent").resolve()
ADAPTER = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()
BASE = Path("results/E3/08_guardagent")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ADAPTER))

from guardagent import GuardAgent
from request_seeact import (
    CodeGEN_Examples,
    User_Request_SeeAct,
    Specification_SeeAct,
    Decomposition_Examples,
)
from utils import get_input_seeact, get_output_seeact

DATA = Path(
    "external/guardagent_dataset/seeact/sample_labeled_all.json"
)

sample = json.loads(DATA.read_text())[0]
record = json.loads((BASE / "e3a_nonthinking.json").read_text())

assert record["sample_annotation_id"] == sample["annotation_id"]

# Restore the official long-term memory structure.
memory = []

for item in CodeGEN_Examples.split("\n\n"):
    item = item.split("Agent input:\n")[-1]
    agent_input = item.split("\nAgent output:\n")[0]
    item = item.split("\nAgent output:\n")[-1]
    agent_output = item.split("\nTask decomposition:\n")[0]
    item = item.split("\nTask decomposition:\n")[-1]
    subtasks = item.split("\nGuardrail code:\n")[0]
    code = item.split("\nGuardrail code:\n")[-1]

    memory.append({
        "agent input": agent_input,
        "agent output": agent_output,
        "subtasks": subtasks,
        "code": code,
    })

agent_input, _, _, output_path = get_input_seeact(
    sample, output_dir=str(DATA.parent)
)
agent_output = get_output_seeact(output_path, 0)

agent = GuardAgent(
    name="guardagent_prompt_test",
    human_input_mode="NEVER",
    code_execution_config=False,
    config_list=[{}],
)

agent.update_memory(3, memory)

# Reuse the saved E3A result instead of calling the API again.
def reuse_decomposition(*args, **kwargs):
    return record["decomposition"]

agent.task_decomposition = reuse_decomposition

prompt = agent.generate_init_message(
    user_request=User_Request_SeeAct,
    agent_specification=Specification_SeeAct,
    agent_input=agent_input,
    agent_output=agent_output,
    agent_task_deco_examples=Decomposition_Examples,
)

assert isinstance(prompt, str) and prompt.strip()
assert record["decomposition"] in prompt

out = BASE / "e3i4_prompt.json"
assert not out.exists(), f"Output exists: {out}"

report = {
    "experiment": "GuardAgent-E3I-4",
    "implementation": "official_guardagent_prompt_builder",
    "model": record["model"],
    "sample_annotation_id": sample["annotation_id"],
    "memory_size": len(memory),
    "num_shots": 3,
    "prompt_chars": len(prompt),
    "decomposition_reused": True,
    "prompt": prompt,
    "full_guardagent_reproduced": False,
}

out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("Memory entries:", len(memory))
print("Few-shot examples:", 3)
print("Prompt characters:", len(prompt))
print("Saved:", out)
print("E3I-4 PASS")
