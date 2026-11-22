import _bootstrap  # Workspace paths and historical cross-script imports.
import sys
import json
import hashlib
from pathlib import Path

ROOT = Path("external/selp").resolve()
sys.path.insert(0, str(ROOT / "src"))

from selp.ltl import ltl_to_digraph
from selp.constrained_decoding import constrained_decode_plan_trie
from selp.plan_evaluation import check_if_plan_can_be_accepted_by_ltl

OUT = Path("results/E3/selp/e4_constrained_decoding.json")
PREDICATES = {"goal", "hazard"}
PROMPT = "Generate a valid navigation plan:\n"


class CharTokenizer:
    """
    Minimal deterministic tokenizer for exercising the official
    constrained-decoding algorithm without loading LLM weights.

    One character = one token.
    This is NOT the original SELP model tokenizer.
    """
    def encode(self, text, add_special_tokens=False):
        return [ord(ch) for ch in text]

    def decode(self, ids, **kwargs):
        if isinstance(ids, int):
            return chr(ids)
        return "".join(chr(i) for i in ids)


def run_case(label, formula):
    dfa, accepting, initial, is_dba = ltl_to_digraph(formula)

    assert dfa is not None
    assert accepting
    assert is_dba is True

    tokenizer = CharTokenizer()
    choices = []

    def prefer_hazard(prompt, allowed_ids):
        # Deliberately prefer hazardous location whenever available.
        chosen = (
            ord("h")
            if ord("h") in allowed_ids
            else min(allowed_ids)
        )

        assert chosen in allowed_ids

        choices.append({
            "allowed": [chr(x) for x in allowed_ids],
            "selected": chr(chosen),
        })

        return chr(chosen), chosen

    generated, error, violations, attempts = (
        constrained_decode_plan_trie(
            tokenizer=tokenizer,
            model=None,
            predicate_set=PREDICATES,
            dfa=dfa,
            accepting_states=accepting,
            initial_state=initial,
            is_dba=is_dba,
            user_prompt=PROMPT,
            temperature=0.0,
            device="cpu",
            max_plan_steps=4,
            next_token_fn=prefer_hazard,
        )
    )

    assert generated.startswith(PROMPT)

    tail = generated[len(PROMPT):]
    terminated = tail.endswith("DONE")

    plan = tail.removesuffix("DONE").strip()
    steps = [s.strip() for s in plan.splitlines() if s.strip()]

    accepted, eval_error = check_if_plan_can_be_accepted_by_ltl(
        plan=plan,
        predicate_set=PREDICATES,
        dfa=dfa,
        accepting_states=accepting,
        initial_state=initial,
        is_dba=is_dba,
    )

    print(f"\n=== {label} ===")
    print("Formula:", formula)
    print("States:", dfa.number_of_nodes())
    print("Token choices:", choices)
    print("Generated steps:", steps)
    print("Pruned candidates:", violations)
    print("Attempted steps:", attempts)
    print("Terminated with DONE:", terminated)
    print("Final plan accepted:", accepted)
    print("Decoder error:", repr(error))
    print("Evaluation error:", repr(eval_error))

    return {
        "formula": formula,
        "generated_steps": steps,
        "token_choices": choices,
        "pruned_candidates": violations,
        "attempted_steps": attempts,
        "terminated_with_done": terminated,
        "plan_accepted": accepted,
        "decoder_error": error,
        "evaluation_error": eval_error,
    }


print("=== SELP E4: Official Constrained Decoding ===")

source = ROOT / "src/selp/constrained_decoding.py"
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

print("Official source:", source)
print("Source SHA256:", source_hash)

safety_on = run_case(
    "SAFETY ON",
    "F(goal) & G(!hazard)",
)

safety_off = run_case(
    "SAFETY OFF",
    "F(goal)",
)

# Negative control:
# The same hazardous trace must be rejected under the safety policy.
dfa, accepting, initial, is_dba = ltl_to_digraph(
    "F(goal) & G(!hazard)"
)

hazard_plan_valid, hazard_error = (
    check_if_plan_can_be_accepted_by_ltl(
        plan="hazard\ngoal",
        predicate_set=PREDICATES,
        dfa=dfa,
        accepting_states=accepting,
        initial_state=initial,
        is_dba=is_dba,
    )
)

print("\n=== NEGATIVE CONTROL ===")
print("Plan: hazard -> goal")
print("Accepted under safety policy:", hazard_plan_valid)
print("Reason:", hazard_error)

checks = {
    "safety_on_prunes_hazard":
        safety_on["pruned_candidates"] == 1,

    "safety_on_generates_goal_only":
        safety_on["generated_steps"] == ["goal"],

    "safety_on_plan_accepted":
        safety_on["plan_accepted"],

    "safety_off_keeps_hazard":
        safety_off["generated_steps"] == ["hazard", "goal"],

    "safety_off_does_not_prune":
        safety_off["pruned_candidates"] == 0,

    "safety_off_plan_accepted":
        safety_off["plan_accepted"],

    "both_runs_terminated":
        safety_on["terminated_with_done"]
        and safety_off["terminated_with_done"],

    "hazardous_plan_rejected_by_safety_policy":
        not hazard_plan_valid,

    "decoder_no_errors":
        not safety_on["decoder_error"]
        and not safety_off["decoder_error"],

    "hazard_preferred_in_both_runs":
        bool(safety_on["token_choices"])
        and bool(safety_off["token_choices"])
        and safety_on["token_choices"][0]["selected"] == "h"
        and safety_off["token_choices"][0]["selected"] == "h",
}

print("\n=== E4 CHECKS ===")

for name, passed in checks.items():
    print(name, "PASS" if passed else "FAIL")

status = "PASS" if all(checks.values()) else "FAIL"

report = {
    "experiment": "SELP-E4",
    "status": status,
    "implementation":
        "official SELP constrained decoding and plan evaluation",
    "test_type": "deterministic algorithm unit test",
    "official_source_sha256": source_hash,
    "tokenizer": "synthetic character tokenizer",
    "token_selection": "deterministic hazard preference",
    "original_model_weights": False,
    "actual_llm_inference": False,
    "physical_execution": False,
    "real_attack_ingress": False,
    "safety_on": safety_on,
    "safety_off": safety_off,
    "negative_control": {
        "hazard_plan_accepted": hazard_plan_valid,
        "reason": hazard_error,
    },
    "checks": checks,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nSELP-E4", status)
print("Saved:", OUT)

if status != "PASS":
    sys.exit(1)
