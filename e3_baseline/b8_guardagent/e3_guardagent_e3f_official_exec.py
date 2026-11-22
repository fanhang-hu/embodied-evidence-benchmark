import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path("external/guardagent").resolve()
sys.path.insert(0, str(ROOT))

from toolset_high import run_code_seeact
from utils import get_input_seeact, get_output_seeact

BASE = Path("results/E3/08_guardagent")
DATA = Path("external/guardagent_dataset/seeact/sample_labeled_all.json")

record = json.loads((BASE / "e3b_codegen.json").read_text())
sample = json.loads(DATA.read_text())[0]

assert record["sample_annotation_id"] == sample["annotation_id"]

raw = record["generated_code"].strip()
code = re.sub(r"^```(?:python|py)?\s*\n", "", raw)
code = re.sub(r"\n```\s*$", "", code)

# Reuse the restricted E3D syntax and call allowlist.
tree = ast.parse(code)

allowed_nodes = (
    ast.Module, ast.Assign, ast.Name, ast.Store, ast.Load,
    ast.Dict, ast.Constant, ast.Call, ast.If, ast.Expr,
    ast.Tuple, ast.Compare, ast.Eq, ast.UnaryOp, ast.Not,
)

for node in ast.walk(tree):
    assert isinstance(node, allowed_nodes), type(node).__name__
    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)
        assert node.func.id in {"CheckRule", "print"}

agent_input, _, _, output_path = get_input_seeact(
    sample, output_dir=str(DATA.parent)
)
agent_output = get_output_seeact(output_path, 0)

# Supply the actual SeeAct output as execution context.
cell = "answer = " + repr(agent_output) + "\n" + code

# Official GuardAgent tool execution.
result = run_code_seeact(cell)

report = {
    "experiment": "GuardAgent-E3F",
    "sample_annotation_id": sample["annotation_id"],
    "ground_truth_label": sample["label"],
    "official_executor": "run_code_seeact",
    "official_checkrule": True,
    "markdown_fence_removed": True,
    "answer_source": "actual_seeact_agent_output",
    "result": result,
    "full_guardagent_reproduced": False
}

out = BASE / "e3f_official_exec.json"
assert not out.exists(), f"Output exists: {out}"

out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

print("=== Official GuardAgent Result ===")
print(result)
print("\nSaved:", out)
