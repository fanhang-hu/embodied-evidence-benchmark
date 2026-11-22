import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import re
from pathlib import Path

BASE = Path("results/E3/08_guardagent")
DATA = Path("external/guardagent_dataset/seeact/sample_labeled_all.json")
SOURCE = Path("external/guardagent/toolset_high.py")
HEADER = Path("external/guardagent/prompts_guard.py")

record = json.loads((BASE / "e3b_codegen.json").read_text())
sample = json.loads(DATA.read_text())[0]

raw = record["generated_code"].strip()
fenced = raw.startswith("```")

# Remove Markdown fences for static parsing only.
code = re.sub(r"^```(?:python|py)?\s*\n", "", raw)
code = re.sub(r"\n```\s*$", "", code)

print("=== GuardAgent E3C: Static Audit ===")
print("Sample:", sample["annotation_id"])
print("Ground-truth label:", sample["label"])
print("Markdown fence present:", fenced)

# Parse code without executing it.
tree = ast.parse(code)
print("Python AST parse: PASS")

def get_assignment(name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(t, ast.Name) and t.id == name
                for t in node.targets
            ):
                return ast.literal_eval(node.value)
    raise ValueError(f"Assignment not found: {name}")

generated_info = get_assignment("user_info")
generated_rules = get_assignment("list_of_rules")
official_info = sample["user_info"]

differences = {
    k: {
        "dataset": official_info.get(k),
        "generated": generated_info.get(k)
    }
    for k in official_info.keys() | generated_info.keys()
    if official_info.get(k) != generated_info.get(k)
}

print("\n=== User Information ===")
print("Facts match:", not differences)
print("Differences:", differences)

assert len(generated_rules) == 1
action, rule = next(iter(generated_rules.items()))

field = rule["info"]
operator = rule["operator"]
required = rule["value"]

if operator == "==":
    satisfied = official_info[field] == required
elif operator == ">=":
    satisfied = official_info[field] >= required
else:
    raise ValueError(f"Unexpected operator: {operator}")

reference_decision = "ALLOW" if satisfied else "DENY"

calls_checkrule = any(
    isinstance(n, ast.Call)
    and isinstance(n.func, ast.Name)
    and n.func.id == "CheckRule"
    for n in ast.walk(tree)
)

print("\n=== Rule Verification ===")
print("Action:", action)
print("Field:", field)
print("Operator:", operator)
print("Required value:", required)
print("Reference decision:", reference_decision)
print("CheckRule found:", calls_checkrule)

# Check whether the generated code defines "answer".
loaded = {
    n.id for n in ast.walk(tree)
    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
}
defined = {
    n.id for n in ast.walk(tree)
    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
}

answer_undefined = "answer" in loaded and "answer" not in defined

# Inspect the official SeeAct execution context.
wrapper_ast = ast.parse(SOURCE.read_text())
wrapper = next(
    n for n in wrapper_ast.body
    if isinstance(n, ast.FunctionDef)
    and n.name == "run_code_seeact"
)
globals_dict = next(
    ast.literal_eval(n.value)
    for n in ast.walk(wrapper)
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name) and t.id == "global_var"
        for t in n.targets
    )
)

header_ast = ast.parse(HEADER.read_text())
header = next(
    ast.literal_eval(n.value)
    for n in header_ast.body
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name) and t.id == "CodeHeader"
        for t in n.targets
    )
)
header_defines_answer = any(
    isinstance(n, ast.Name)
    and n.id == "answer"
    and isinstance(n.ctx, ast.Store)
    for n in ast.walk(ast.parse(header))
)

answer_unavailable = (
    answer_undefined
    and "answer" not in globals_dict
    and not header_defines_answer
)

print("\n=== Execution Compatibility ===")
print("Markdown fence needs removal:", fenced)
print("Undefined answer:", answer_undefined)
print("Official wrapper provides answer:", "answer" in globals_dict)
print("CodeHeader defines answer:", header_defines_answer)
print("Unresolved answer reference:", answer_unavailable)
print("Code executed: False")

issues = []
if fenced:
    issues.append("markdown_fence")
if differences:
    issues.append("sample_fact_mismatch")
if not calls_checkrule:
    issues.append("missing_checkrule")
if answer_unavailable:
    issues.append("undefined_answer")

report = {
    "experiment": "GuardAgent-E3C",
    "status": "STATIC_AUDIT_COMPLETE",
    "sample_annotation_id": sample["annotation_id"],
    "ground_truth_label": sample["label"],
    "facts_match": not differences,
    "fact_differences": differences,
    "reference_decision": reference_decision,
    "calls_checkrule": calls_checkrule,
    "execution_blockers": issues,
    "generated_code_executed": False,
}

OUT = BASE / "e3c_static_audit.json"
OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

print("\nGUARDAGENT-E3C STATIC_AUDIT_COMPLETE")
print("Execution blockers:", issues)
print("Saved:", OUT)
