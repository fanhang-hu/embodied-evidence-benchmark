import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
from pathlib import Path

from openai import OpenAI
from hippo.utils.git_diff import git_diff
import hippo.simulation.semanticverifllm.llm_semantic_verification as judge

BASE = Path("results/E3/07_percepttwin")
MODEL = "deepseek-v4-pro"

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

results = []

for name, filename in [
    ("unsafe", "e1e_corrupted.json"),
    ("safe", "e1f_positive.json"),
]:
    r = json.loads((BASE / filename).read_text())
    old = r["native_before"]
    new = r["native_after"]

    assert isinstance(old, dict) and isinstance(new, dict)

    target = next(
        k for k in old if k.startswith("StoveKnob|")
    )

    history = (
        f'0: ToggleObjectOn(robot="robot0", '
        f'target_object="{target}")'
    )

    diff = git_diff(old, new, "Executing_The_Plan")
    assert diff and "isToggled" in diff

    full = (
        "EXECUTED PLAN:\n"
        f"{history}\n\n"
        "DIFF BETWEEN FIRST AND FINAL STATES:\n"
        f"{diff}"
    )

    calls = []

    def llm_adapter(prompt, model, max_tokens=1000, **kwargs):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tokens,
            extra_body={"thinking": {"type": "disabled"}},
        )

        answer = response.choices[0].message.content or ""

        calls.append({
            "prompt": prompt,
            "answer": answer,
            "model": response.model,
        })

        return response, answer

    # Replace only the model adapter, not the original judge.
    judge.LLM = llm_adapter

    entry = {
        "case": name,
        "source": str(BASE / filename),
        "task": r["task"],
        "native_state_replay_only": True,
        "unity_restarted": False,
    }

    try:
        verdict = judge.LLM_verify_final_state(
            MODEL, r["task"], full, diff, history
        )

        entry.update({
            "status": "PARSED",
            "decision": type(verdict).__name__,
            "reason": verdict.reason,
            "is_valid": verdict.is_valid,
        })

    except Exception as e:
        entry.update({
            "status": "ERROR",
            "error": f"{type(e).__name__}: {e}",
        })

    entry["model_calls"] = calls
    results.append(entry)

    (BASE / "p22_final_state_pair.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2)
    )

    print(
        name,
        entry.get("decision", entry.get("error")),
        "valid=", entry.get("is_valid"),
        flush=True,
    )

print("Saved:", BASE / "p22_final_state_pair.json")
