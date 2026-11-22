import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path

BASE = Path("results/E3/08_guardagent")
SRC = BASE / "e3i5b_tool_probe.json"
OUT = BASE / "e3i5c_bridge.json"

assert SRC.exists()
assert not OUT.exists(), f"Output exists: {OUT}"

official = Path("external/guardagent").resolve()
adapter = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()

sys.path.insert(0, str(official))
sys.path.insert(0, str(adapter))

from guardagent import GuardAgent

record = json.loads(SRC.read_text())
calls = record["tool_calls"]

assert len(calls) == 1
call = calls[0]

assert call["name"] == "python"
assert isinstance(call["arguments"]["cell"], str)

cell = call["arguments"]["cell"]

# Translate only the protocol, not the Python code.
legacy_call = {
    "name": "python",
    "arguments": json.dumps(
        call["arguments"], ensure_ascii=False
    ),
}

captured = []

def safe_record_only(cell):
    # Never execute model-generated code in this test.
    captured.append(cell)
    return "SAFE_TOOL_BRIDGE_OK"

guard = GuardAgent(
    name="guardagent_bridge_test",
    human_input_mode="NEVER",
    llm_config=False,
    code_execution_config=False,
    config_list=[{}],
)

guard.register_function(
    function_map={"python": safe_record_only}
)

# Use AutoGen 0.2.0's legacy function_call format.
message = {
    "role": "assistant",
    "content": None,
    "function_call": legacy_call,
}

reply = guard.generate_reply(messages=[message])

passed = (
    isinstance(reply, dict)
    and reply.get("role") == "function"
    and reply.get("name") == "python"
    and reply.get("content") == "SAFE_TOOL_BRIDGE_OK"
    and captured == [cell]
    and guard.code == cell
)

report = {
    "experiment": "GuardAgent-E3I-5C",
    "source": str(SRC),
    "source_protocol": "tool_calls",
    "target_protocol": "function_call",
    "official_guardagent_dispatch_used": True,
    "tool_name": "python",
    "received_code": captured,
    "reply": reply,
    "executor": "safe_record_only",
    "generated_code_executed": False,
    "pass": passed,
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("=== GuardAgent Tool Bridge ===")
print("Source protocol: tool_calls")
print("Target protocol: function_call")
print("Tool:", legacy_call["name"])
print("Code received:", captured)
print("Official GuardAgent reply:", reply)
print("Generated code executed: False")
print("Saved:", OUT)

assert passed, "Bridge verification failed"
print("E3I-5C PASS")
