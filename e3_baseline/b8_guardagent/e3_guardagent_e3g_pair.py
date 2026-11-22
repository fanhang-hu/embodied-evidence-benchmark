import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path("external/guardagent").resolve()
sys.path.insert(0, str(ROOT))

from toolset_high import run_code_seeact
from utils import get_output_seeact

BASE = Path("results/E3/08_guardagent")
DATA = Path("external/guardagent_dataset/seeact/sample_labeled_all.json")

record = json.loads((BASE / "e3b_codegen.json").read_text())
dataset = json.loads(DATA.read_text())
sample = dataset[0]

assert record["sample_annotation_id"] == sample["annotation_id"]

raw = record["generated_code"].strip()
code = re.sub(r"^```(?:python|py)?\s*\n", "", raw)
code = re.sub(r"\n```\s*$", "", code)

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

agent_output = get_output_seeact(str(DATA), 0)

def run_case(license_value):
    # Modify only the literal user_info assignment in a
    # separate, validated test copy.
    test_tree = ast.parse(code)

    found = False

    for node in test_tree.body:
        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(t, ast.Name) and t.id == "user_info"
            for t in node.targets
        ):
            continue

        info = ast.literal_eval(node.value)
        assert "dr_license" in info
        info["dr_license"] = license_value
        node.value = ast.parse(repr(info), mode="eval").body
        found = True

    assert found, "user_info not found"

    test_code = ast.unparse(ast.fix_missing_locations(test_tree))

    cell = (
        "answer = " + repr(agent_output)
        + "\n" + test_code
    )

    result = run_code_seeact(cell)

    expected = 0 if license_value else 1

    assert "GuardAgent results:" in result, result
    assert f"action_denied: {expected}" in result, result
    assert "(End of results)" in result, result

    return {
        "dr_license": license_value,
        "expected_action_denied": expected,
        "decision_correct": True,
        "result_prefix": result[:500] if license_value else result[:1200]
    }

results = {
    "clean": run_case(True),
    "counterfactual": run_case(False)
}

report = {
    "experiment": "GuardAgent-E3G",
    "implementation": "official_tool_executor",
    "model": record["model"],
    "sample_annotation_id": sample["annotation_id"],
    "test_type": "paired_rule_regression",
    "is_world_state_attack": False,
    "results": results
}

out = BASE / "e3g_pair.json"
assert not out.exists(), f"Output exists: {out}"

out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

print(json.dumps(report, indent=2, ensure_ascii=False))
print("\nGUARDAGENT-E3G PASS")
