import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import subprocess
import shutil
from pathlib import Path

OUT = Path("results/E3/08_guardagent/e1c_sandbox_probe.json")

print("=== GuardAgent E1C: Bubblewrap Sandbox Probe ===")

assert shutil.which("bwrap"), "Bubblewrap not installed"
assert Path("/usr/bin/python3").exists()

# Trusted probe only. No LLM-generated code.
PROBE = r'''
import os
import json
import socket
from pathlib import Path

checks = {}

# Host home directory must not be mounted.
checks["home_hidden"] = not Path("/home").exists()
checks["root_home_hidden"] = not Path("/root").exists()
checks["host_project_hidden"] = not Path(
    str(_bootstrap.ROOT / "external/guardagent")
).exists()

# Host environment credentials must not be inherited.
checks["api_keys_hidden"] = all(
    name not in os.environ
    for name in [
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY"
    ]
)

# System directories must be read-only.
try:
    Path("/usr/guardagent_e1c_write_probe").write_text("test")
    checks["system_readonly"] = False
except OSError:
    checks["system_readonly"] = True

# The sandbox should have private temporary storage.
try:
    path = Path("/work/probe.txt")
    path.write_text("sandbox-test")
    checks["private_work_writable"] = (
        path.read_text() == "sandbox-test"
    )
except OSError:
    checks["private_work_writable"] = False

# Test that an external IP cannot be connected.
try:
    with socket.socket(
        socket.AF_INET, socket.SOCK_STREAM
    ) as sock:
        sock.settimeout(1)
        result = sock.connect_ex(("1.1.1.1", 53))
        checks["network_blocked"] = result != 0
except OSError:
    checks["network_blocked"] = True

print(json.dumps({
    "checks": checks,
    "passed": all(checks.values())
}))
'''

cmd = [
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
    cmd += ["--ro-bind", "/lib64", "/lib64"]

if Path("/bin").exists():
    cmd += ["--ro-bind", "/bin", "/bin"]

cmd += [
    "--proc", "/proc",
    "--dev", "/dev",
    "--tmpfs", "/tmp",
    "--tmpfs", "/work",
    "--setenv", "HOME", "/work",
    "--setenv", "PATH", "/usr/bin:/bin",
    "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
    "--chdir", "/work",
    "--",
    "/usr/bin/python3",
    "-c",
    PROBE,
]

try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
        },
    )
    print("Return code:", result.returncode)
    print("Stdout:", result.stdout.strip())
    print("Stderr:", result.stderr.strip()[:1000])

    try:
        probe_result = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        probe_result = None

    passed = (
        result.returncode == 0
        and probe_result is not None
        and probe_result.get("passed") is True
    )

    report = {
        "experiment": "GuardAgent-E1C",
        "status": "PASS" if passed else "FAIL",
        "sandbox_type": "bubblewrap",
        "probe": probe_result,
        "returncode": result.returncode,
        "stderr": result.stderr[:2000],
        "llm_generated_code_executed": False,
        "sandbox_security_fully_verified": False,
        "resource_limits_configured": False,
    }

except Exception as e:
    passed = False
    report = {
        "experiment": "GuardAgent-E1C",
        "status": "FAIL",
        "error": str(e),
    }
    print("Error:", e)

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n=== E1C SUMMARY ===")
if report.get("probe"):
    for name, value in report["probe"]["checks"].items():
        print(f"{name}: {'PASS' if value else 'FAIL'}")

print("GUARDAGENT-E1C", report["status"])
print("Saved:", OUT)

if not passed:
    raise SystemExit(1)
