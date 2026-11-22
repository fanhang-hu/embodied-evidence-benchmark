import _bootstrap  # Workspace paths and historical cross-script imports.
import sys
import json
import importlib.metadata as md
from pathlib import Path

ROOT = Path("external/guardagent").resolve()
sys.path.insert(0, str(ROOT))

OUT = Path("results/E3/08_guardagent/e2d_offline_compat.json")

print("=== GuardAgent E2D: Offline Compatibility ===")

versions = {}
for pkg in ["pyautogen", "openai", "httpx", "httpcore"]:
    try:
        versions[pkg] = md.version(pkg)
    except md.PackageNotFoundError:
        versions[pkg] = None

print("Versions:", versions)

checks = {}
errors = {}

def run_check(name, fn):
    try:
        fn()
        checks[name] = True
        print(name, "PASS")
    except Exception as exc:
        checks[name] = False
        errors[name] = f"{type(exc).__name__}: {exc}"
        print(name, "FAIL:", errors[name])

def check_official_imports():
    from guardagent import GuardAgent
    from autogen.agentchat import AssistantAgent, UserProxyAgent
    assert issubclass(GuardAgent, UserProxyAgent)
    assert AssistantAgent is not None

def check_autogen_instances():
    from autogen.agentchat import AssistantAgent
    from guardagent import GuardAgent

    assistant = AssistantAgent(
        name="e2d_offline_assistant",
        llm_config=False,
        code_execution_config=False,
    )

    guard = GuardAgent(
        name="e2d_offline_guard",
        human_input_mode="NEVER",
        llm_config=False,
        code_execution_config=False,
        config_list=[],
    )

    assert assistant is not None
    assert guard is not None

def check_openai_client():
    from openai import OpenAI

    # Dummy credentials and a nonfunctional local endpoint.
    # Construction only: no network request.
    client = OpenAI(
        api_key="sk-offline-placeholder",
        base_url="http://127.0.0.1:9/v1",
    )
    assert client is not None
    client.close()

run_check("official_imports", check_official_imports)
run_check("autogen_instances", check_autogen_instances)
run_check("openai_client_construction", check_openai_client)

passed = all(checks.values())

report = {
    "experiment": "GuardAgent-E2D",
    "status": "PASS" if passed else "COMPATIBILITY_BLOCKED",
    "versions": versions,
    "checks": checks,
    "errors": errors,
    "real_api_key_used": False,
    "network_request_sent": False,
    "llm_inference": False,
    "generated_code_executed": False,
    "original_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n=== E2D SUMMARY ===")
print("GUARDAGENT-E2D", report["status"])
print("Saved:", OUT)

if not passed:
    sys.exit(1)
