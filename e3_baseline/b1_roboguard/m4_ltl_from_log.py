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

from roboguard.synthesis import ControlSynthesis

ROOT = Path("results/baseline_audit")
LOG = ROOT / "m4_deepseek_clean_retry.log"

text = LOG.read_text()

# Spot parse_error 会打印无法解析的合并 LTL。
matches = re.findall(r"^>>>\s*(.+)$", text, re.MULTILINE)

if not matches:
    raise RuntimeError("No LTL formula found in error log")

raw = next(
    (s for s in matches if "inspect_person_1" in s),
    None
)

if raw is None:
    raise RuntimeError("Target LTL formula not found")

print("=== 1. Recovered LTL ===")
print(raw)

# RoboGuard 的 clean_formula() 已把
# inspect(person_1, "*") 变成 inspect_person_1, "*"
# 此处仅移除不兼容的第二参数占位符。
pattern = r'(\binspect_[A-Za-z0-9_]+)\s*,\s*["\']\*["\']'

normalized, count = re.subn(
    pattern,
    r'\1',
    raw
)

print("\n=== 2. Syntax Normalization ===")
print("Replacements:", count)
print("Normalized LTL:")
print(normalized)

print("\n=== 3. Spot Parsing ===")

parse_ok = False
verdict = None
steps = None

try:
    formula = spot.formula(normalized)
    parse_ok = True
    print("SPOT_PARSE_PASSED")
    print("Formula:", formula)
except Exception as e:
    print("SPOT_PARSE_FAILED:", str(e)[:500])

print("\n=== 4. Original RoboGuard Validator ===")

if parse_ok:
    try:
        checker = ControlSynthesis([normalized])

        verdict, steps = checker.validate_action_sequence(
            [("inspect", "person_1")]
        )

        print("Candidate:", "inspect(person_1)")
        print("Accepted:", verdict)
        print("Steps:", steps)

    except Exception as e:
        print(
            "VALIDATION_FAILED:",
            type(e).__name__,
            str(e)[:500]
        )

report = {
    "source": str(LOG),
    "experiment": "DeepSeek clean graph",
    "implementation": "offline_syntax_adaptation",
    "raw_aggregated_ltl": raw,
    "normalized_ltl": normalized,
    "normalization_count": count,
    "spot_parse_success": parse_ok,
    "adapted_verdict": verdict,
    "adapted_steps": steps,
    "note": (
        "Formula recovered from Spot error log. "
        "Original model JSON and reasoning are unavailable. "
        "Not an original RoboGuard verdict."
    )
}

output = ROOT / "m4_ltl_from_log.json"

output.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\nSaved:", output)
print("OFFLINE LTL DIAGNOSTIC COMPLETED")
