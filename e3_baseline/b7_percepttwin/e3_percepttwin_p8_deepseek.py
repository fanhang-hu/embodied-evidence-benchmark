import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import traceback
from pathlib import Path
from openai import OpenAI

import hippo.simulation.semanticverifllm.llm_semantic_verification as native

BASE = Path("results/E3/07_percepttwin")
BASE.mkdir(parents=True, exist_ok=True)

MODEL = "deepseek-v4-pro"
OUT = BASE / "p8_deepseek_judge.json"

if not os.getenv("DEEPSEEK_API_KEY"):
    raise SystemExit("BLOCKED: DEEPSEEK_API_KEY not set")

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

record = {
    "experiment": "PerceptTwin-P8-DeepSeek",
    "baseline_type": "adapted_native_component",
    "original_verifier": "LLM_verify_diff",
    "original_prompt_and_parser": True,
    "backend": "DeepSeek Chat Completions",
    "model": MODEL,
    "thinking": "disabled",
    "unity_executed": False,
    "status": "STARTED",
}

def deepseek_llm(
    prompt,
    gpt_version,
    max_tokens=128,
    temperature=0,
    stop=None,
    logprobs=1,
    frequency_penalty=0,
    ignore_cache=False,
):
    response = client.chat.completions.create(
        model=gpt_version,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )

    content = response.choices[0].message.content or ""

    record["raw_response"] = content
    record["response_model"] = response.model
    record["finish_reason"] = response.choices[0].finish_reason
    record["usage"] = (
        response.usage.model_dump()
        if response.usage else None
    )

    return response, content

# 仅在本次 Python 进程中替换底层 LLM 调用。
# 原版 Prompt、LLM_verify_diff 和结果解析保持不变。
native.LLM = deepseek_llm

task = "Move the blue cube into the cardboard box."
action = "PickupObject(blue cube)"
pure_diff = (
    "- isPickedUp: false\n"
    "+ isPickedUp: true"
)
history = f"0: {action}"
diff = (
    f"ALL ACTIONS TO DATE:\n{history}\n\n"
    f"DIFF OF LAST ACTION:\n{pure_diff}"
)

record.update({
    "input_type": "illustrative_smoke_case",
    "task": task,
    "action": action,
    "diff": diff,
})

print("=== PerceptTwin P8: DeepSeek Native Judge ===")
print("Model:", MODEL)
print("Official verifier: LLM_verify_diff")
print("Official source modified: NO")
print("Calling DeepSeek API...")

try:
    result = native.LLM_verify_diff(
        MODEL,
        task,
        diff,
        pure_diff,
        history,
        action,
    )

    record.update({
        "status": "PASS",
        "decision": type(result).__name__,
        "is_valid": result.is_valid,
        "reason": result.reason,
        "official_prompt": result.prompt,
    })

    print("Decision:", record["decision"])
    print("Is valid:", record["is_valid"])
    print("Reason:", record["reason"])
    print("P8 DEEPSEEK NATIVE JUDGE PASS")

except Exception as exc:
    record["status"] = "ERROR"
    record["error"] = repr(exc)
    traceback.print_exc()
    raise

finally:
    OUT.write_text(
        json.dumps(record, ensure_ascii=False, indent=2)
    )
    print("Saved:", OUT)
