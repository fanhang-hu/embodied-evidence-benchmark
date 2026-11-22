import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import sys
from pathlib import Path

ROOT = Path("e3_baseline/b8_guardagent/guardagent_deepseek_adapter").resolve()
sys.path.insert(0, str(ROOT))

from config import model_config
from autogen import AssistantAgent

BASE = Path("results/E3/08_guardagent")
OUT = BASE / "e3i3_autogen_probe.json"

assert not OUT.exists(), f"Output already exists: {OUT}"

model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
cfg = model_config(model)

agent = AssistantAgent(
    name="guardagent_autogen_probe",
    system_message=(
        "You are a compatibility test assistant. "
        "Reply with exactly: AUTOGEN_DEEPSEEK_OK"
    ),
    llm_config={
        "config_list": [cfg],
        "temperature": 0,
        "timeout": 60,
        "cache_seed": None,
    },
)

reply = agent.generate_reply(
    messages=[
        {
            "role": "user",
            "content": "Return the required compatibility test string."
        }
    ]
)

print("Model:", model)
print("Reply:", repr(reply))

report = {
    "experiment": "GuardAgent-E3I-3",
    "test": "autogen_deepseek_connection",
    "model": model,
    "endpoint": cfg["base_url"],
    "reply": reply,
    "expected": "AUTOGEN_DEEPSEEK_OK",
    "pass": isinstance(reply, str)
            and reply.strip() == "AUTOGEN_DEEPSEEK_OK",
    "full_guardagent_reproduced": False,
}

OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("Saved:", OUT)
print(
    "E3I-3 PASS" if report["pass"]
    else "E3I-3 CHECK FAILED"
)
