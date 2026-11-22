import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import json
import re
from pathlib import Path
from collections import Counter

ROOT = Path.cwd()
NATIVE = ROOT / "external/PerceptTwin/hippo"
SCRIPTS = ROOT / "e3_baseline/b7_percepttwin"
BASE = ROOT / "results/E3/07_percepttwin"
BASE.mkdir(parents=True, exist_ok=True)

assert NATIVE.is_dir(), "PerceptTwin source missing"

# Locate four categories of relevant code.
KEYWORDS = {
    "A_STATE_PRODUCER": [
        "update_from_ai2thor",
        "coerce_ai2thor_metadata_objects",
        "controller.last_event",
        "metadata[\"objects\"]",
        "metadata['objects']",
    ],
    "B_SHARED_WORLD_STATE": [
        "RuntimeObjectContainer",
        "current_object_container",
        "resolve_spatial_attributes",
        "as_llmjson",
    ],
    "C_SAFETY_AND_EXECUTION": [
        "llm_verify_diff_alignment",
        "LLM_verify_final_state",
        "apply_skill",
        "gen_plan",
    ],
    "D_RESEARCHER_INJECTION": [
        "reported_parents",
        "pan_parentReceptacles",
        "preexec_decision",
        "fresh_pan_parents",
    ],
}

native_files = sorted(NATIVE.rglob("*.py"))
adapter_files = sorted(
    p for p in SCRIPTS.glob("e3_percepttwin_*.py")
    if any(
        x in p.name
        for x in (
            "e1e", "e2_", "e2b_",
            "p15", "p16", "p24b", "p25"
        )
    )
)

assert native_files, "No native Python files"
assert adapter_files, "No experiment scripts"

records = []
definitions = []
errors = []

for origin, paths in [
    ("native", native_files),
    ("research_adapter", adapter_files),
]:
    for path in paths:
        relative = str(path.relative_to(ROOT))

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )
            tree = ast.parse(text)
        except (OSError, SyntaxError) as exc:
            errors.append({
                "file": relative,
                "error": str(exc),
            })
            continue

        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef,
                 ast.ClassDef)
            ):
                if any(
                    word in node.name
                    for words in KEYWORDS.values()
                    for word in words
                ):
                    definitions.append({
                        "origin": origin,
                        "file": relative,
                        "line": node.lineno,
                        "name": node.name,
                    })

        for line_no, line in enumerate(
            text.splitlines(), 1
        ):
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("#")
            ):
                continue

            for category, words in KEYWORDS.items():
                if any(word in line for word in words):
                    records.append({
                        "origin": origin,
                        "category": category,
                        "file": relative,
                        "line": line_no,
                        "code": stripped[:240],
                    })

report = {
    "experiment": "E2-D1_Boundary_Audit",
    "native_files": len(native_files),
    "adapter_files": len(adapter_files),
    "definitions": definitions,
    "matches": records,
    "syntax_errors": errors,
    "runtime_flow_verified": False,
    "attack_surface_verified": False,
}

out = BASE / "e2d1_boundary_audit.json"
out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("=== E2-D1 TRUST BOUNDARY AUDIT ===")
print("Native files:", len(native_files))
print("Adapter files:", len(adapter_files))
print("Total matches:", len(records))
print("Syntax errors:", len(errors))

for category in KEYWORDS:
    print("\n===", category, "===")

    for origin in ("native", "research_adapter"):
        hits = [
            x for x in records
            if x["category"] == category
            and x["origin"] == origin
        ]

        print(f"\n[{origin}] {len(hits)} matches")

        for x in hits[:12]:
            print(
                f"{x['file']}:{x['line']}: "
                f"{x['code']}"
            )

print("\n=== FUNCTION DEFINITIONS ===")

for x in definitions[:30]:
    print(
        x["origin"],
        x["file"],
        x["line"],
        x["name"]
    )

print("\nSaved:", out)
print("E2-D1 STATIC AUDIT COMPLETE")
print("Runtime trust boundary still requires verification")
