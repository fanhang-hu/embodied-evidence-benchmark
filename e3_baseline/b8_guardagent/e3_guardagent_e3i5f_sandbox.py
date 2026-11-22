import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import re
import resource
import subprocess
from pathlib import Path

BASE = Path("results/E3/08_guardagent")
SRC = BASE / "e3i5d_real_toolcall.json"
AUDIT = BASE / "e3i5e_bridge.json"
OUT = BASE / "e3i5f_sandbox.json"

assert SRC.is_file()
assert AUDIT.is_file()
assert not OUT.exists(), f"Output exists: {OUT}"

record = json.loads(SRC.read_text())
audit = json.loads(AUDIT.read_text())

assert record["valid_python_tool_call"] is True
assert audit["static_pass"] is True
assert audit["bridge_pass"] is True

cell = record["tool_calls"][0]["arguments"]["cell"]

code = re.sub(
    r"^```(?:python|py)?\s*\n", "", cell.strip()
)
code = re.sub(r"\n```\s*$", "", code)

# Repeat the E3I-5E AST restrictions before execution.
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

# Official code runs inside the child sandbox, not the host.
child = """
import sys

sys.path.insert(0, "/ga")

from toolset_high import run_code_seeact

cell = sys.stdin.read()
result = run_code_seeact(cell)

print(result)
"""

official = Path("external/guardagent").resolve()
assert (official / "tools.py").is_file()
assert (official / "toolset_high.py").is_file()
assert (official / "prompts_guard.py").is_file()

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
    "--ro-bind", str(official), "/ga",
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
    "/usr/bin/python3",
    "-I", "-S", "-B",
    "-c", child,
]

def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (256 * 1024 * 1024, 256 * 1024 * 1024)
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

proc = subprocess.run(
    command,
    input=code,
    text=True,
    capture_output=True,
    timeout=8,
    check=False,
    env={"PATH": "/usr/bin:/bin", "LANG": "C"},
    preexec_fn=limits,
)

stdout = proc.stdout
stderr = proc.stderr

official_result = (
    "GuardAgent results:" in stdout
    and "(End of results)" in stdout
)

report = {
    "experiment": "GuardAgent-E3I-5F",
    "implementation": "official_executor_in_bwrap",
    "official_checkrule": True,
    "official_run_code_seeact": True,
    "sandbox": "bubblewrap",
    "model": record["model"],
    "sample_annotation_id": record["sample_annotation_id"],
    "returncode": proc.returncode,
    "stdout": stdout,
    "stderr": stderr,
    "official_result_received": official_result,
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("=== GuardAgent E3I-5F ===")
print("Return code:", proc.returncode)
print("Official result received:", official_result)
print("=== STDOUT ===")
print(stdout[:1500])
print("=== STDERR ===")
print(stderr[:1500])
print("Saved:", OUT)

if proc.returncode == 0 and official_result:
    print("E3I-5F PASS")
else:
    print("E3I-5F NEEDS INSPECTION")
