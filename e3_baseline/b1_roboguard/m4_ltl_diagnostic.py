import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import re
import sys
from pathlib import Path

import spot

sys.path.insert(
    0,
    str(Path("external/RoboGuard/src").resolve())
)

from roboguard.generator import ContextualGrounding
from roboguard.synthesis import ControlSynthesis

ROOT = Path("results/baseline_audit")
DATA = ROOT / "m4_deepseek_clean.json"

record = json.loads(DATA.read_text())

specs = record.get("specifications")
if not specs:
    raise RuntimeError("No generated LTL specifications saved")

constraints = ContextualGrounding.gather_specification_propositions(
    specs
)

print("=== 1. Raw Generated Constraints ===")

for i, c in enumerate(constraints, 1):
    print(f"{i}. {c}")

# 仅转换 inspect(object, "*") 为 inspect(object)。
# 这与原版计划检查器忽略 vlm_query 的行为对应。
# 不允许删除整个安全规则，也不转换其他参数形式。
PATTERN = re.compile(
    r'\binspect\(\s*([A-Za-z_][A-Za-z_0-9]*)'
    r'\s*,\s*["\']\*["\']\s*\)'
)

normalized = []
raw_failures = []
normalized_failures = []

print("\n=== 2. Spot Parsing Audit ===")

for i, original in enumerate(constraints, 1):
    raw_formula = ControlSynthesis.clean_formula(None, original)

    try:
        spot.formula(raw_formula)
        raw_status = "PASS"
    except Exception as e:
        raw_status = "FAIL"
        raw_failures.append(i)

    fixed = PATTERN.sub(r'inspect(\1)', original)

    try:
        fixed_formula = ControlSynthesis.clean_formula(None, fixed)
        spot.formula(fixed_formula)
        fixed_status = "PASS"
    except Exception as e:
        fixed_status = "FAIL"
        normalized_failures.append(i)

    normalized.append(fixed)

    print(f"\nConstraint {i}")
    print("Original:", original)
    print("Normalized:", fixed)
    print("Raw parse:", raw_status)
    print("Normalized parse:", fixed_status)

print("\n=== 3. Offline Plan Validation ===")

verdict = None
steps = None

if not normalized_failures:
    try:
        checker = ControlSynthesis(normalized)

        verdict, steps = checker.validate_action_sequence(
            [("inspect", "person_1")]
        )

        print("Plan:", [("inspect", "person_1")])
        print("Accepted:", verdict)
        print("Steps:", steps)

    except Exception as e:
        print("Validation error:", type(e).__name__, str(e)[:300])
else:
    print("Skipped: normalized constraints still contain errors")

report = {
    "model": record.get("model"),
    "source_status": record.get("status"),
    "implementation": "offline_syntax_adaptation_only",
    "raw_constraints": constraints,
    "normalized_constraints": normalized,
    "raw_parse_failures": raw_failures,
    "normalized_parse_failures": normalized_failures,
    "adapted_verdict": verdict,
    "adapted_steps": steps,
}

output = ROOT / "m4_ltl_diagnostic.json"
output.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== Summary ===")
print("Total constraints:", len(constraints))
print("Raw parse failures:", raw_failures)
print("Normalized parse failures:", normalized_failures)
print("Adapted verdict:", verdict)
print("Saved:", output)
print("LTL DIAGNOSTIC COMPLETED")
