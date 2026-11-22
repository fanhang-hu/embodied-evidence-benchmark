import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
from pathlib import Path
from importlib.metadata import version

import openai

from hippo.simulation.semanticverifllm.llm_semantic_verification import (
    LLM_verify_diff,
)

BASE = Path("results/E3/07_percepttwin")
BASE.mkdir(parents=True, exist_ok=True)

JUDGE = "gpt-5-2025-08-07"

print("=== PerceptTwin P8: Native LLM Judge ===")
print("OpenAI SDK:", version("openai"))
print("Judge:", JUDGE)
print("API key configured:", bool(os.getenv("OPENAI_API_KEY")))
print("Custom base URL:", bool(os.getenv("OPENAI_BASE_URL")))
print("Responses API available:", hasattr(openai, "responses"))

if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit(
        "BLOCKED: OPENAI_API_KEY is not configured."
    )

if not hasattr(openai, "responses"):
    raise SystemExit(
        "BLOCKED: Installed OpenAI SDK lacks Responses API."
    )

task = "Move the blue cube into the cardboard box."

action = "PickupObject(blue cube)"

pure_diff = """
- isPickedUp: false
+ isPickedUp: true
"""

history = f"0: {action}"

diff = f"""
ALL ACTIONS TO DATE:
{history}

DIFF OF LAST ACTION:
{pure_diff}
"""

print("Calling official LLM_verify_diff()...")

result = LLM_verify_diff(
    JUDGE,
    task,
    diff,
    pure_diff,
    history,
    action,
)

record = {
    "experiment": "PerceptTwin-P8",
    "type": "native_llm_judge_component",
    "input_origin": "illustrative_smoke_case",
    "official_judge_code": True,
    "unity_executed": False,
    "model": JUDGE,
    "task": task,
    "action": action,
    "decision": type(result).__name__,
    "is_valid": result.is_valid,
    "reason": result.reason,
    "raw_response": result.response,
}

out = BASE / "p8_native_judge.json"

out.write_text(
    json.dumps(record, indent=2, ensure_ascii=False)
)

print("Decision:", record["decision"])
print("Valid:", record["is_valid"])
print("Reason:", record["reason"])
print("Saved:", out)
print("P8 NATIVE LLM JUDGE COMPLETE")
