import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import re
import hashlib
from pathlib import Path

import spot

from roboguard.prompts.base import BASE_RULES
from roboguard.generator import ContextualGrounding
from roboguard.synthesis import ControlSynthesis

SRC = Path(
    "results/E3/01_roboguard/"
    "e3a6_repeat01/e3a5_live_clean.json"
)
OUT = Path(
    "results/E3/01_roboguard/"
    "e3a6_clean_offline_recheck.json"
)

assert SRC.is_file(), f"Missing saved response: {SRC}"
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

record = json.loads(SRC.read_text())

assert record["model"] == "deepseek-flash"
assert record["finish_reason"] == "stop"
assert record["raw_response"]
assert record["status"] == "ERROR"

def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True).encode()
    ).hexdigest()

assert record["rules_hash"] == sha(BASE_RULES)

# 完全使用本轮已保存的模型响应，不重新调用 API。
specs = json.loads(record["raw_response"])
assert isinstance(specs, dict)

adapted = {}

for rule, entries in specs.items():
    assert isinstance(entries, list)
    adapted[rule] = []

    for entry in entries:
        if isinstance(entry, dict):
            constraint = entry["constraint"]
            reasoning = entry["reasoning"]
        else:
            assert isinstance(entry, list) and len(entry) == 2
            constraint, reasoning = entry

        assert isinstance(constraint, str)
        assert isinstance(reasoning, str)

        adapted[rule].append({
            "constraint": constraint,
            "reasoning": reasoning
        })

constraints = (
    ContextualGrounding.gather_specification_propositions(
        adapted
    )
)

# 只允许规范化 inspect(object, *) 这种确定的通配符写法。
# 原版验证器将 inspect 的第二个 VLM query 参数投影掉。
wildcard = re.compile(
    r'\binspect\(\s*([A-Za-z_][A-Za-z0-9_]*)'
    r'\s*,\s*(?:\*|["\']\*["\'])\s*\)'
)

normalized = []
changes = []

for original in constraints:
    fixed, count = wildcard.subn(
        r'inspect(\1)', original
    )

    if re.search(r'\binspect\([^)]*,', fixed):
        raise ValueError(
            f"Unsupported inspect syntax: {fixed}"
        )

    # 每条约束都必须能够被 Spot 解析。
    spot.formula(
        ControlSynthesis.clean_formula(None, fixed)
    )

    normalized.append(fixed)

    if count:
        changes.append({
            "before": original,
            "after": fixed,
            "count": count
        })

print("=== E3-A6 Clean Offline Replay ===")
print("Saved original status:", record["status"])
print("Raw response SHA256:", hashlib.sha256(
    record["raw_response"].encode()
).hexdigest())
print("Constraints:", len(constraints))

print("\n=== Syntax Normalization ===")
for item in changes:
    print(item["before"])
    print("  ->", item["after"])

print("\n=== All Normalized LTL ===")
for item in normalized:
    print(" ", item)

checker = ControlSynthesis(normalized)
accepted, steps = checker.validate_action_sequence(
    [tuple(x) for x in record["plan"]]
)

control_checker = ControlSynthesis(normalized)
benign, benign_steps = (
    control_checker.validate_action_sequence(
        [("goto", "ground_18")]
    )
)

print("\n=== Verification ===")
print("Clean decision:", "ALLOW" if accepted else "BLOCK")
print("Benign control:", "ALLOW" if benign else "BLOCK")
print("Steps:", steps)

result = {
    "source_file": str(SRC),
    "source_record_status": record["status"],
    "source_raw_response_sha256": hashlib.sha256(
        record["raw_response"].encode()
    ).hexdigest(),
    "implementation": "RoboGuard-adapted-DeepSeek",
    "replay_type": "offline_saved_model_response",
    "original_gpt4o": False,
    "physical_execution": False,
    "original_constraints": constraints,
    "normalized_constraints": normalized,
    "syntax_changes": changes,
    "clean_accepted": bool(accepted),
    "benign_control_accepted": bool(benign),
    "steps": steps,
    "benign_steps": benign_steps
}

OUT.write_text(json.dumps(
    result, indent=2, ensure_ascii=False
))

print("\nE3-A6 CLEAN OFFLINE RECHECK COMPLETE")
print("Saved:", OUT)
