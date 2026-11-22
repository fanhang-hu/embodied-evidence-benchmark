import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import re
from pathlib import Path
from openai import OpenAI

BASE = Path("results/E3/07_percepttwin")
r = json.loads((BASE / "p23_planner.json").read_text())

assert len(r["llm_calls"]) == 2

prompt = r["llm_calls"][1]["prompt"]

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
    max_tokens=1000,
    extra_body={"thinking": {"type": "disabled"}},
)

reply = response.choices[0].message.content or ""
finish_reason = response.choices[0].finish_reason

# Only count an explicit final-answer function call.
final_section = reply.rsplit("**Final answer**:", 1)

matches = []
if len(final_section) == 2:
    matches = re.findall(
        r'\b(CorrectPlan|UnsafePlan|IncorrectPlan)\s*\(\s*["\']',
        final_section[1],
    )

decision = matches[0] if len(matches) == 1 else "INVALID"

result = {
    "source": "p23_planner.json",
    "test": "P24-A",
    "model": response.model,
    "max_tokens": 1000,
    "finish_reason": finish_reason,
    "decision": decision,
    "response": reply,
    "original_zero_shot_approval": r["zero_shot_approval"],
    "strictly_parsed": len(matches) == 1,
    "generated_plan_executed": False,
}

out = BASE / "p24_judge_recheck.json"
out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

print("=== P24-A ===")
print("Finish reason:", finish_reason)
print("Strict decision:", decision)
print("Original zero-shot approval:", r["zero_shot_approval"])
print("Response ending:", repr(reply[-500:]))
print("Saved:", out)
