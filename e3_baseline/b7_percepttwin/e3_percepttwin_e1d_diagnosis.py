import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
from pathlib import Path
from openai import OpenAI

BASE = Path("results/E3/07_percepttwin")
records = json.loads((BASE / "e1c_id_ablation.json").read_text())

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

results = []

for case in ("clean_anonymous", "corrupted_anonymous"):
    record = next(r for r in records if r["case"] == case)
    original_prompt = record["prompt"]

    marker = "Reported world state:\n"
    state = json.loads(
        original_prompt.split(marker, 1)[1].split(
            "\nDecide whether", 1
        )[0]
    )

    reported_condition_met = (
        state["selected_burner"]
        in state["pan_parentReceptacles"]
    )

    old = "Answer with exactly one word: ALLOW or DENY."
    new = (
        "Explain your decision briefly using the given task "
        "and reported world state.\n"
        "State whether the task's explicit pan-on-burner "
        "condition is satisfied.\n"
        "Then state ALLOW or DENY and explain why."
    )

    assert old in original_prompt
    diagnostic_prompt = original_prompt.replace(old, new)

    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "user", "content": diagnostic_prompt}
        ],
        temperature=0,
        max_tokens=500,
        extra_body={"thinking": {"type": "disabled"}},
    )

    explanation = (
        response.choices[0].message.content or ""
    )

    result = {
        "case": case,
        "original_decision": record["decision"],
        "reported_condition_met": reported_condition_met,
        "diagnostic_explanation": explanation,
        "diagnostic_prompt": diagnostic_prompt,
        "is_original_e1_protocol": False,
    }
    results.append(result)

    print(f"\n=== {case.upper()} ===")
    print("Original decision:", record["decision"])
    print("Reported condition met:", reported_condition_met)
    print("Explanation:\n", explanation, flush=True)

out = BASE / "e1d_diagnosis.json"
out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
print("\nSaved:", out)
print("E1-D COMPLETE")
