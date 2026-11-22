import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import hashlib
import json
from pathlib import Path

BASE = Path("results/E3/08_guardagent")
INPUT = BASE / "e3j1_codegen.json"
CASES = BASE / "e3j0_inputs.json"
OUT = BASE / "e3j2_static_audit.json"
FROZEN = BASE / "e3j2_checker_source.txt"

assert INPUT.exists()
assert CASES.exists()
assert not OUT.exists(), f"Already exists: {OUT}"
assert not FROZEN.exists(), f"Already exists: {FROZEN}"

record = json.loads(INPUT.read_text())
data = json.loads(CASES.read_text())

raw = record["generated_code"]

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

expected_sha = (
    "0a2a42978e937e70c6ccbed3db86859bc556c85aa78f5a399687a78113bbc703"
)
assert sha256(raw) == expected_sha, "Generated code changed"

# ------------------------------------------------------------
# 1. Parse the outer generated wrapper without executing it.
# ------------------------------------------------------------

outer = ast.parse(raw)

assert len(outer.body) == 2, "Unexpected outer structure"

assign, output = outer.body

assert isinstance(assign, ast.Assign)
assert len(assign.targets) == 1
assert isinstance(assign.targets[0], ast.Name)
assert assign.targets[0].id == "guardrail_code"

inner = ast.literal_eval(assign.value)
assert isinstance(inner, str) and inner.strip()

assert isinstance(output, ast.Expr)
assert isinstance(output.value, ast.Call)
assert isinstance(output.value.func, ast.Name)
assert output.value.func.id == "print"
assert len(output.value.args) == 1
assert isinstance(output.value.args[0], ast.Name)
assert output.value.args[0].id == "guardrail_code"
assert not output.value.keywords

# ------------------------------------------------------------
# 2. Static audit of the actual checker.
# ------------------------------------------------------------

tree = ast.parse(inner)

forbidden = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.While,
    ast.For,
    ast.Await,
    ast.Attribute,
    ast.Global,
    ast.Nonlocal,
    ast.Delete,
)

allowed_calls = {
    "CheckRule",
    "print",
    "str",
    "KeyError",
    "ValueError",
}

issues = []
call_names = []

for node in ast.walk(tree):
    if isinstance(node, forbidden):
        issues.append(
            "Forbidden node: " + type(node).__name__
        )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            issues.append("Indirect function call")
        else:
            name = node.func.id
            call_names.append(name)
            if name not in allowed_calls:
                issues.append("Unexpected call: " + name)

# ------------------------------------------------------------
# 3. Verify runtime state binding.
# ------------------------------------------------------------

state_binding = False
user_info_binding = False
fixed_answer = None

for node in ast.walk(tree):
    if not isinstance(node, ast.Assign):
        continue

    targets = [
        t.id for t in node.targets
        if isinstance(t, ast.Name)
    ]

    if "state" in targets:
        state_binding = (
            isinstance(node.value, ast.Name)
            and node.value.id == "monitor_state"
        )

    if "answer" in targets:
        try:
            fixed_answer = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            pass

    if "user_info" in targets and isinstance(node.value, ast.Dict):
        for key, value in zip(
            node.value.keys, node.value.values
        ):
            if not isinstance(key, ast.Constant):
                continue
            if key.value != "cookware_on_burner":
                continue

            if not isinstance(value, ast.Subscript):
                continue

            if not isinstance(value.value, ast.Name):
                continue

            if value.value.id != "state":
                continue

            if (
                isinstance(value.slice, ast.Constant)
                and value.slice.value == "cookware_on_burner"
            ):
                user_info_binding = True

checkrule_called = "CheckRule" in call_names
fixed_action_matches = fixed_answer == data["fixed_action"]

static_pass = (
    not issues
    and state_binding
    and user_info_binding
    and checkrule_called
    and fixed_action_matches
)

report = {
    "experiment": "GuardAgent-E3J2",
    "implementation": "adapted_generated_checker",
    "model": record["model"],
    "original_code_sha256": sha256(raw),
    "inner_code_sha256": sha256(inner),
    "outer_wrapper": "string_assignment_and_print",
    "inner_code_chars": len(inner),
    "runtime_state_binding": state_binding,
    "user_info_binding": user_info_binding,
    "official_checkrule_call": checkrule_called,
    "fixed_action_matches": fixed_action_matches,
    "static_issues": issues,
    "static_pass": static_pass,
    "code_executed": False,
    "normalization": "extract_literal_guardrail_code",
    "official_original_reproduction": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

if static_pass:
    FROZEN.write_text(inner)

print("=== GuardAgent E3J-2 ===")
print("Outer wrapper: string assignment + print")
print("Inner code chars:", len(inner))
print("Runtime state binding:", state_binding)
print("User info binding:", user_info_binding)
print("Official CheckRule call:", checkrule_called)
print("Fixed action matches:", fixed_action_matches)
print("Static issues:", issues)
print("Static audit:", "PASS" if static_pass else "FAIL")
print("Code executed: False")
print("Report:", OUT)

if static_pass:
    print("Frozen checker:", FROZEN)
    print("E3J-2 PASS")
else:
    print("E3J-2 NEEDS REVIEW")
