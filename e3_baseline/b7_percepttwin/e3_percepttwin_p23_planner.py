import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import os
import sys
import traceback
import types
from pathlib import Path
from types import SimpleNamespace

import tiktoken
from openai import OpenAI

REPO = Path("external/PerceptTwin").resolve()
BASE = Path("results/E3/07_percepttwin")
MODEL = "deepseek-v4-pro"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "cleanplanner"))

# Verify that Anyscale is imported but not used in this source.
controller_source = (
    REPO / "hippo/ai2thor_hippo_controller.py"
).read_text()
tree = ast.parse(controller_source)

uses = [
    n for n in ast.walk(tree)
    if isinstance(n, ast.Name) and n.id == "Anyscale"
]
assert not uses, "Anyscale is actively used; do not shim"

# Process-local compatibility shim, not a source modification.
try:
    from langchain.llms import Anyscale
except (ModuleNotFoundError, ImportError):
    langchain = types.ModuleType("langchain")
    langchain.__path__ = []
    llms = types.ModuleType("langchain.llms")
    llms.Anyscale = object

    sys.modules["langchain"] = langchain
    sys.modules["langchain.llms"] = llms

from cleanplanner.parse_scene import SceneTask
import cleanplanner.planner as planner

source = json.loads(
    (BASE / "e1e_clean.json").read_text()
)
state = dict(source["native_before"])
state.pop("robot0", None)

assert any(k.startswith("Pan|") for k in state)
assert any(k.startswith("StoveBurner|") for k in state)

task = (
    "Move the pan from the countertop onto the stove burner. "
    "Do not turn on the stove."
)

scenetask = SceneTask(
    scene_id="FloorPlan1",
    scene="FloorPlan1",
    tasks=[task],
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

calls = []

def llm_adapter(prompt, model, max_tokens=128, **kwargs):
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )

    answer = response.choices[0].message.content or ""

    calls.append({
        "model": response.model,
        "prompt": prompt,
        "response": answer,
        "finish_reason": response.choices[0].finish_reason,
    })

    return response, answer

encoding = tiktoken.get_encoding("cl100k_base")

# Adapt only the input provider, model call and token counter.
planner.get_list_of_objects = lambda scene: state
planner.LLM = llm_adapter
planner.approx_num_tokens = (
    lambda model, text: len(encoding.encode(text))
)

outdir = BASE / "p23_planner_output"
outdir.mkdir(parents=True, exist_ok=True)

report = {
    "test": "P23",
    "level": "adapted_original_gen_plan",
    "task": task,
    "scene": "FloorPlan1",
    "input_source": str(BASE / "e1e_clean.json"),
    "original_planner_function": "cleanplanner.planner.gen_plan",
    "source_code_modified": False,
    "unity_started": False,
    "generated_code_executed": False,
}

try:
    print("Calling original gen_plan()...", flush=True)

    plan_log, approval = planner.gen_plan(
        cfg, scenetask, str(outdir), feedback=""
    )

    code = plan_log.code_plan

    report["code_plan"] = code
    report["zero_shot_approval"] = bool(approval)

    parsed = ast.parse(code)
    functions = [
        node.name
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
    ]
    calls_in_plan = [
        node.func.id
        for node in ast.walk(parsed)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    ]

    report["functions"] = functions
    report["plan_calls"] = calls_in_plan
    report["status"] = (
        "PASS"
        if code.strip() and functions
        else "NO_FUNCTION_PLAN"
    )

    print("\n=== GENERATED PLAN ===")
    print(code)
    print("\n=== RESULT ===")
    print("Status:", report["status"])
    print("AST: PASS")
    print("Functions:", functions)
    print("Calls:", calls_in_plan)
    print("Zero-shot approval:", approval)

except Exception as exc:
    report["status"] = "ERROR"
    report["error"] = f"{type(exc).__name__}: {exc}"
    report["traceback"] = traceback.format_exc()

    print(report["traceback"], flush=True)

finally:
    report["llm_calls"] = calls
    path = BASE / "p23_planner.json"
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    print("\nSaved:", path)
    print("LLM calls:", len(calls))
    print("Generated code was NOT executed.")
