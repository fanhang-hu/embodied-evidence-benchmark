import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import os
import re
import resource
import subprocess
import sys
from pathlib import Path

BASE = Path("results/E3/08_guardagent")
raw = json.loads(
    (BASE / "e3b_codegen.json").read_text()
)["generated_code"]

normalized = re.sub(
    r"^```(?:python|py)?\s*\n", "", raw.strip()
)
normalized = re.sub(r"\n```\s*$", "", normalized)

# Only permit the narrowly scoped generated checker from E3B.
tree = ast.parse(normalized)

allowed_nodes = (
    ast.Module, ast.Assign, ast.Name, ast.Store, ast.Load,
    ast.Dict, ast.Constant, ast.Call, ast.If, ast.Expr,
    ast.Tuple, ast.Compare, ast.Eq, ast.UnaryOp, ast.Not,
)

for node in ast.walk(tree):
    if not isinstance(node, allowed_nodes):
        raise ValueError(
            f"Disallowed AST node: {type(node).__name__}"
        )

allowed_calls = {"CheckRule", "print"}

for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id in allowed_calls
        ):
            raise ValueError("Unexpected function call")

# Build a temporary minimal module for the isolated child.
# The rule checker uses the same comparison semantics as
# this single official CheckRule case (operator ==).
harness = '''
def CheckRule(rules, user_info):
    denied = False
    violations = {}
    for action, rule in rules.items():
        if rule["operator"] != "==":
            raise ValueError("unsupported operator")
        if user_info[rule["info"]] != rule["value"]:
            denied = True
            violations[action] = rule["violation"]
    return denied, violations
'''

tests = {
    "normalized_with_context": normalized,
}

def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (256 * 1024 * 1024, 256 * 1024 * 1024)
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))

results = {}

for name, generated in tests.items():
    source = harness + "\nanswer = 'TEST_AGENT_OUTPUT'\n" + generated

    command = [
        "bwrap",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-net",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
    ]

    if Path("/lib64").exists():
        command += ["--ro-bind", "/lib64", "/lib64"]

    if Path("/bin").exists():
        command += ["--ro-bind", "/bin", "/bin"]

    command += [
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--tmpfs", "/work",
        "--chdir", "/work",
        "--setenv", "HOME", "/work",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--",
        "/usr/bin/python3", "-I", "-S", "-B",
        "-c", source,
    ]

    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            preexec_fn=limits,
        )

        result = {
            "returncode": proc.returncode,
            "stdout": proc.stdout[:2000],
            "stderr": proc.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        result = {
            "returncode": None,
            "error": "TIMEOUT",
        }

    results[name] = result

    print(f"\n=== {name} ===")
    print(json.dumps(result, indent=2))

report = {
    "experiment": "GuardAgent-E3E",
    "method": "isolated_semantic_harness",
    "official_toolset_high_executed": False,
    "checkrule_implementation": "restricted_equivalence",
    "results": results,
}

out = BASE / "e3e_executor.json"
out.write_text(json.dumps(report, indent=2))

print("\nGUARDAGENT-E3E COMPLETE")
print("Saved:", out)
