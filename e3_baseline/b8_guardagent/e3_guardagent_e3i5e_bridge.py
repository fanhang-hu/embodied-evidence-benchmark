import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path("results/E3/08_guardagent")
SRC = BASE / "e3i5d_real_toolcall.json"
OUT = BASE / "e3i5e_bridge.json"

assert SRC.exists()
assert not OUT.exists(), f"Output exists: {OUT}"

official = Path("external/guardagent").resolve()
adapter = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()

sys.path.insert(0, str(official))
sys.path.insert(0, str(adapter))

from guardagent import GuardAgent

record = json.loads(SRC.read_text())
assert record["valid_python_tool_call"]

calls = record["tool_calls"]
assert len(calls) == 1
assert calls[0]["name"] == "python"

cell = calls[0]["arguments"]["cell"]
assert isinstance(cell, str) and cell.strip()

# Step 1: Static audit. Do not execute the generated code.
code = re.sub(
    r"^```(?:python|py)?\s*\n", "", cell.strip()
)
code = re.sub(r"\n```\s*$", "", code)

allowed_nodes = (
    ast.Module, ast.Assign, ast.Name, ast.Store, ast.Load,
    ast.Dict, ast.Constant, ast.Call, ast.If, ast.Expr,
    ast.Tuple, ast.Compare, ast.Eq, ast.UnaryOp, ast.Not,
)

static_issues = []
facts_match = None
calls_checkrule = False

try:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            static_issues.append(
                f"Disallowed AST node: {type(node).__name__}"
            )
        if isinstance(node, ast.Call):
            if not (
                isinstance(node.func, ast.Name)
                and node.func.id in {"CheckRule", "print"}
            ):
                static_issues.append("Unexpected function call")
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "CheckRule"
            ):
                calls_checkrule = True

    assignments = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "user_info"
                ):
                    assignments["user_info"] = ast.literal_eval(
                        node.value
                    )

    DATA = Path(
        "external/guardagent_dataset/seeact/sample_labeled_all.json"
    )
    sample = json.loads(DATA.read_text())[0]
    assert record["sample_annotation_id"] == sample["annotation_id"]
    facts_match = assignments.get("user_info") == sample["user_info"]

except (SyntaxError, ValueError, KeyError, TypeError) as exc:
    static_issues.append(f"{type(exc).__name__}: {exc}")

static_pass = (
    not static_issues
    and facts_match is True
    and calls_checkrule
)

# Step 2: Bridge the protocol. Record code only; never execute it.
legacy_call = {
    "name": "python",
    "arguments": json.dumps(
        calls[0]["arguments"], ensure_ascii=False
    ),
}

captured = []

def record_only(cell):
    captured.append(cell)
    return "SAFE_TOOL_BRIDGE_OK"

guard = GuardAgent(
    name="guardagent_real_bridge",
    human_input_mode="NEVER",
    llm_config=False,
    code_execution_config=False,
    config_list=[{}],
)

guard.register_function(
    function_map={"python": record_only}
)

reply = guard.generate_reply(messages=[{
    "role": "assistant",
    "content": None,
    "function_call": legacy_call,
}])

bridge_pass = (
    isinstance(reply, dict)
    and reply.get("role") == "function"
    and reply.get("name") == "python"
    and reply.get("content") == "SAFE_TOOL_BRIDGE_OK"
    and captured == [cell]
    and guard.code == cell
)

report = {
    "experiment": "GuardAgent-E3I-5E",
    "source": str(SRC),
    "code_sha256": hashlib.sha256(
        cell.encode()
    ).hexdigest(),
    "code_chars": len(cell),
    "static_pass": static_pass,
    "static_issues": static_issues,
    "facts_match": facts_match,
    "calls_checkrule": calls_checkrule,
    "bridge_pass": bridge_pass,
    "official_guardagent_dispatch": True,
    "executor": "record_only",
    "generated_code_executed": False,
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("=== GuardAgent E3I-5E ===")
print("Code chars:", len(cell))
print("Static audit:", "PASS" if static_pass else "NEEDS REVIEW")
print("Facts match:", facts_match)
print("Calls CheckRule:", calls_checkrule)
print("Static issues:", static_issues)
print("Official function bridge:", "PASS" if bridge_pass else "FAIL")
print("Code executed: False")
print("Saved:", OUT)

assert bridge_pass, "Function bridge failed"
print("E3I-5E BRIDGE PASS")
