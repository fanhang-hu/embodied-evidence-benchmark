"""E6-4B: read-only static producer-consumer trace."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (
    "results/E6/15_dataflow/"
    "e6_dataflow_20261025_01"
)

TARGETS = {
    "e4_validation/simulator.py": (
        "objects",
        "step",
        "start_controller",
    ),
    "e5_validation/protocol.py": (
        "paired_view",
        "guarded",
    ),
    "e5_validation/task_recovery_v2.py": (
        "protected_query",
    ),
    "e6_validation/recovery_pilot.py": (
        "paired_public",
    ),
}

TOKENS = (
    "metadata",
    "last_event",
    ".step(",
    "Controller(",
    "world_state",
    "scene_graph",
    "observation",
    "LowLevelPlanner",
)

PIPELINE_TOKENS = (
    "paired_public(",
    "protected_query(",
    "guarded(",
    "lookup(",
    "monitor(",
    "step(controller",
    "state(objects(",
    "planner_input =",
)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def definitions(source):
    tree = ast.parse(source)
    return [
        node for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
    ]


def owned_by(line_number, functions):
    candidates = [
        node for node in functions
        if node.lineno <= line_number <= node.end_lineno
    ]
    if not candidates:
        return "<module>"
    node = min(
        candidates,
        key=lambda f: f.end_lineno - f.lineno,
    )
    return node.name


def main():
    require(not OUT.exists(), "E6-4B output exists")

    report = {
        "status": "STATIC_TRACE_COMPLETE",
        "native_T1_demonstrated": False,
        "new_unity_calls": 0,
        "new_llm_calls": 0,
        "local_functions": {},
        "e6_call_sites": [],
        "safeagentbench": {},
        "framework_imports": [],
    }

    print("===== 1. EXISTING E6 TRUST PATH =====")

    for relative, wanted in TARGETS.items():
        path = ROOT / relative
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()

        selected = []

        for node in definitions(source):
            if node.name not in wanted:
                continue

            item = {
                "name": node.name,
                "line_start": node.lineno,
                "line_end": node.end_lineno,
                "source": "\n".join(
                    lines[node.lineno - 1:node.end_lineno]
                ),
            }
            selected.append(item)

            print(f"\n{relative}:{node.lineno} {node.name}")
            print(item["source"][:3500])

        report["local_functions"][relative] = selected

    print("\n===== 2. E6 RUNNER CALL SITES =====")

    runner = ROOT / "e6_validation/recovery_pilot.py"
    lines = runner.read_text(encoding="utf-8").splitlines()

    for number, line in enumerate(lines, 1):
        if not any(t in line for t in PIPELINE_TOKENS):
            continue

        if number < 244:
            continue

        item = {
            "line": number,
            "text": line.strip(),
        }
        report["e6_call_sites"].append(item)

        if len(report["e6_call_sites"]) <= 45:
            print(f"L{number}: {line.strip()}")

    print("\n===== 3. SAFEAGENTBENCH CONTROLLER =====")

    external = ROOT / (
        "external/SafeAgentBench/"
        "low_level_controller/low_level_controller.py"
    )
    require(
        external.is_file(),
        "SafeAgentBench controller source missing",
    )

    text = external.read_text(
        encoding="utf-8", errors="replace"
    )
    lines = text.splitlines()
    funcs = definitions(text)
    tree = ast.parse(text)

    classes = [
        {
            "name": node.name,
            "line": node.lineno,
            "end": node.end_lineno,
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]

    hits = []
    for number, line in enumerate(lines, 1):
        if not any(token in line for token in TOKENS):
            continue

        hits.append({
            "line": number,
            "function": owned_by(number, funcs),
            "text": line.strip()[:240],
        })

    selected_functions = []
    seen = set()

    for hit in hits:
        name = hit["function"]
        if name in seen or name == "<module>":
            continue
        seen.add(name)
        selected_functions.append(name)

    report["safeagentbench"] = {
        "source": str(external.relative_to(ROOT)),
        "classes": classes,
        "matched_lines": len(hits),
        "candidate_methods": selected_functions,
        "hits": hits,
    }

    print("Classes:", [c["name"] for c in classes])
    print("Matching lines:", len(hits))
    print("Methods with matching lines:")
    for name in selected_functions[:35]:
        print(" ", name)

    print("\nFirst 35 source hits:")
    for hit in hits[:35]:
        print(
            f"L{hit['line']} "
            f"[{hit['function']}] "
            f"{hit['text']}"
        )

    print("\n===== 4. FRAMEWORK IMPORT CROSS-CHECK =====")

    for subdir in (
        "e4_validation",
        "e5_validation",
        "e6_validation",
    ):
        for path in sorted((ROOT / subdir).rglob("*.py")):
            content = path.read_text(
                encoding="utf-8", errors="replace"
            )

            if re.search(
                r"SafeAgentBench|low_level_controller|LowLevelPlanner",
                content,
                flags=re.IGNORECASE,
            ):
                relative = str(path.relative_to(ROOT))
                report["framework_imports"].append(relative)
                print(relative)

    if not report["framework_imports"]:
        print(
            "No direct textual references from E4/E5/E6 "
            "modules to SafeAgentBench controller"
        )

    OUT.mkdir(parents=True, exist_ok=False)

    (OUT / "trace.json").write_text(
        json.dumps(
            report, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    print("\nE6-4B STATIC DATAFLOW TRACE: COMPLETE")
    print("T1 exploitation: NOT DEMONSTRATED")
    print("New Unity calls: 0")
    print("New LLM calls: 0")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
