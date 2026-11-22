import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import hashlib
import json
import os
import re
import sys
import traceback
import types
from pathlib import Path
from types import SimpleNamespace

import tiktoken
from openai import OpenAI

ROOT = Path.cwd()
REPO = ROOT / "external/PerceptTwin"
BASE = ROOT / "results/E3/07_percepttwin"
MODEL = "deepseek-v4-pro"

p23 = json.loads(
    (BASE / "p23_planner.json").read_text()
)
failed = json.loads(
    (BASE / "p24b_native_plan_first_fail.json").read_text()
)
source = json.loads(
    (BASE / "e1e_clean.json").read_text()
)

old_plan = p23["code_plan"]

assert "CONDITION_NotUnderAnotherObject" in str(
    failed.get("error")
), "First-failure evidence not found"

assert failed["status"] == "ERROR"
assert p23["status"] == "PASS"

state = dict(source["native_before"])
state.pop("robot0", None)

pan = next(
    x for x in state if x.startswith("Pan|")
)

# Same import compatibility as P23.
sys.path[:0] = [
    str(REPO),
    str(REPO / "cleanplanner"),
]

controller_src = (
    REPO / "hippo/ai2thor_hippo_controller.py"
).read_text()

assert not any(
    isinstance(n, ast.Name) and n.id == "Anyscale"
    for n in ast.walk(ast.parse(controller_src))
)

try:
    from langchain.llms import Anyscale
except (ModuleNotFoundError, ImportError):
    m = types.ModuleType("langchain")
    m.__path__ = []
    llms = types.ModuleType("langchain.llms")
    llms.Anyscale = object
    sys.modules["langchain"] = m
    sys.modules["langchain.llms"] = llms

from cleanplanner.parse_scene import SceneTask, PlanLog
import cleanplanner.planner as planner

scene = SceneTask(
    scene_id="FloorPlan1",
    scene="FloorPlan1",
    tasks=[p23["task"]],
    robots_ids=[1],
    robots=[{"name": "robot1"}],
)

cfg = SimpleNamespace(
    planner=SimpleNamespace(
        llm=MODEL,
        ignore_cache=True,
    ),
    feedback=SimpleNamespace(
        judge_llm=MODEL,
    ),
)

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

trace = []

def llm_adapter(
    prompt, model, max_tokens=128, **kwargs
):
    # More output budget to avoid P23 truncation.
    budget = max(1000, int(max_tokens))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=budget,
        extra_body={
            "thinking": {"type": "disabled"}
        },
    )

    reply = (
        response.choices[0].message.content or ""
    )

    if "We detected that this plan was faulty" in prompt:
        phase = "repair_decision"
    elif "Your job is to verify the validity of the plan" in prompt:
        phase = "zero_shot"
    else:
        phase = "regenerated_plan"

    trace.append({
        "phase": phase,
        "max_tokens": budget,
        "finish_reason":
            response.choices[0].finish_reason,
        "response": reply,
        "prompt": prompt,
    })

    return response, reply

planner.LLM = llm_adapter
planner.get_list_of_objects = lambda _: state

enc = tiktoken.get_encoding("cl100k_base")
planner.approx_num_tokens = (
    lambda _, prompt: len(enc.encode(prompt))
)

# Extract the unchanged original decision function.
# This avoids importing Hydra / WandB / OmegaConf.
loop_path = REPO / "cleanplanner/run_full_loop.py"
loop_source = loop_path.read_text()
loop_ast = ast.parse(loop_source)

function = next(
    n for n in loop_ast.body
    if isinstance(n, ast.FunctionDef)
    and n.name == "ask_if_plan_can_be_fixed"
)

assert function.decorator_list == []

namespace = {
    "LLM": llm_adapter,
    "PlanLog": PlanLog,
}

exec(
    compile(
        ast.fix_missing_locations(
            ast.Module(
                body=[function],
                type_ignores=[],
            )
        ),
        str(loop_path),
        "exec",
    ),
    namespace,
)

original_decider = namespace[
    "ask_if_plan_can_be_fixed"
]

prior = PlanLog(
    llm=MODEL,
    scenetask=scene,
    num_input_tokens=0,
    num_output_tokens=0,
    code_plan=old_plan,
    llm_outputs={"code_plan": old_plan},
)

# Reconstruct the official feedback fields from
# the verified first P24-B failure.
feedback = {
    "Type": "CONDITION_NotUnderAnotherObject",
    "Error message":
        f"Object {pan} is under another object.",
}

report = {
    "test": "P25",
    "failure_evidence":
        "p24b_native_plan_first_fail.json",
    "failure_origin":
        "Actual first P24-B precondition failure",
    "feedback": feedback,
    "feedback_reconstructed": True,
    "decision_function":
        "ask_if_plan_can_be_fixed",
    "planner_function": "gen_plan",
    "official_full_loop_executed": False,
    "unity_started": False,
    "generated_code_executed": False,
    "loop_source_sha256": hashlib.sha256(
        loop_source.encode()
    ).hexdigest(),
}

try:
    print(
        "=== P25-A: ORIGINAL REPLAN DECISION ===",
        flush=True,
    )

    approve = original_decider(
        cfg, prior, feedback
    )

    decision_text = trace[-1]["response"]

    markers = {
        k: k in decision_text
        for k in (
            "APPROVE REPLAN",
            "CANCEL REPLAN",
        )
    }

    report["original_decision"] = (
        "APPROVE REPLAN"
        if approve else "CANCEL REPLAN"
    )

    report["decision_markers"] = markers
    report["decision_unambiguous"] = (
        sum(markers.values()) == 1
    )

    print(
        "Decision:", report["original_decision"]
    )
    print(
        "Unambiguous:",
        report["decision_unambiguous"],
    )

    # Exact feedback structure used by run_scenetask.
    feedback_text = (
        "# ------\n\n"
        "# Last time you tried to generate a plan "
        "for this task and scene, "
        "you generated the following:\n"
        f'"""{old_plan}"""\n\n'
        "# But the plan failed, "
        "and you got this error message:\n"
        f'#{feedback["Error message"]}\n'
        "# ------"
    )

    report["feedback_text"] = feedback_text

    print(
        "\n=== P25-B: ORIGINAL GEN_PLAN WITH FEEDBACK ===",
        flush=True,
    )

    output_dir = BASE / "p25_replan_output"
    output_dir.mkdir(
        parents=True, exist_ok=True
    )

    # Diagnostic even if decider says CANCEL:
    # in that case it is NOT an official-loop replan.
    plan_log, approval = planner.gen_plan(
        cfg,
        scene,
        str(output_dir),
        feedback=feedback_text,
    )

    code = plan_log.code_plan

    # Parse only; never execute LLM code.
    tree = ast.parse(code)

    functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]

    report.update({
        "new_plan": code,
        "changed_plan":
            code.strip() != old_plan.strip(),
        "ast_valid": True,
        "functions": functions,
        "native_zero_shot_approval":
            bool(approval),
        "new_plan_executed": False,
        "replan_follows_original_decision":
            bool(approve),
        "status":
            "REPLAN_GENERATED"
            if functions
            else "REPLAN_NO_FUNCTION",
    })

    last_reply = trace[-1]["response"]

    final_part = last_reply.rsplit(
        "**Final answer**:", 1
    )[-1]

    labels = re.findall(
        r"\b(CorrectPlan|UnsafePlan|IncorrectPlan)\s*\(",
        final_part,
    )

    report["strict_zero_shot_labels"] = labels

    print("Replan AST: PASS")
    print("Functions:", functions)
    print(
        "Changed plan:",
        report["changed_plan"],
    )
    print(
        "Zero-shot original:",
        approval,
    )
    print(
        "Zero-shot strict labels:",
        labels,
    )

    print("\n=== GENERATED PLAN ===")
    print(code)

except Exception as exc:
    report["status"] = "ERROR"
    report["error"] = (
        f"{type(exc).__name__}: {str(exc)[:700]}"
    )
    report["traceback"] = traceback.format_exc(
        limit=6
    )
    print("P25 ERROR:", report["error"])

finally:
    report["llm_calls"] = trace

    outfile = BASE / "p25_feedback_replan.json"
    outfile.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\nSaved:", outfile)
    print("API calls:", len(trace))
    print("Generated code NOT executed.")
