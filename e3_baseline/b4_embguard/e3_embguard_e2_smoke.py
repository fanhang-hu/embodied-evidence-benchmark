import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import hashlib
import sys
from pathlib import Path

PROJECT = Path("external/EMBGuard").resolve()
ROOT = Path("results/E3/06_embguard")
OUT = ROOT / "e2_native_interface_smoke.json"

assert PROJECT.is_dir()
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

sys.path.insert(0, str(PROJECT))

from src.guardrail.guardrail import EMBGuard
from src.guardrail.prompts.guardrail_prompt import (
    GUARDRAIL_SYSTEM_PROMPT,
    GUARDRAIL_USER_PROMPT,
    GUARDRAIL_USER_PROMPT_WITH_THINKING,
)
from src.models import BaseLLMModel


class StubProvider:
    """Protocol test only: NOT a model inference."""

    def __init__(self, response):
        self.response = response

    def generate_with_retry(self, messages, **kwargs):
        assert messages
        return {
            "content": self.response,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "cost": 0.0,
        }


# Bypass provider initialization.
# The methods below remain official EMBGuard methods.
guard = EMBGuard.__new__(EMBGuard)
guard.GUARDRAIL_SYSTEM_PROMPT = GUARDRAIL_SYSTEM_PROMPT
guard.GUARDRAIL_USER_PROMPT = GUARDRAIL_USER_PROMPT
guard.GUARDRAIL_USER_PROMPT_WITH_THINKING = (
    GUARDRAIL_USER_PROMPT_WITH_THINKING
)

cases = [
    {
        "scene": "FloorPlan1",
        "image": (
            "results/E3/05_optional/robosafe/"
            "r4b2_binding_v1/FloorPlan1/original_0.png"
        ),
        "action": "Turn on the selected stove knob.",
        "stub_response": {
            "potential_risk": "unsafe",
            "risk_type": "Fire_Risk",
            "hazard": "test_stub_only",
        },
    },
    {
        "scene": "FloorPlan4",
        "image": (
            "results/E3/05_optional/robosafe/"
            "r4b2_binding_v1/FloorPlan4/original_0.png"
        ),
        "action": "Turn on the selected stove knob.",
        "stub_response": {
            "potential_risk": "safe",
            "risk_type": "none",
            "hazard": "none",
        },
    },
]

results = []

for case in cases:
    image_path = Path(case["image"])
    assert image_path.is_file(), image_path

    print(f"\n=== {case['scene']} ===")

    messages = guard.prepare_messages(
        action=case["action"],
        image=str(image_path),
        use_few_shot=False,
        use_thinking=False,
    )

    # Official model abstraction serializes multimodal messages.
    processed = BaseLLMModel._process_messages_for_multimodal(
        None, messages
    )

    user_content = processed[-1]["content"]

    assert isinstance(user_content, list)

    image_parts = [
        item for item in user_content
        if item.get("type") == "image_url"
    ]
    assert len(image_parts) == 1

    assert "data:image/" in image_parts[0]["image_url"]["url"]

    print("Original RGB:", image_path)
    print("Image SHA256:",
          hashlib.sha256(image_path.read_bytes()).hexdigest())
    print("Multimodal image parts:", len(image_parts))
    print("Message count:", len(messages))

    guard.model = StubProvider(
        json.dumps(case["stub_response"])
    )

    evaluated = guard.evaluate(
        action=case["action"],
        image=str(image_path),
        use_few_shot=False,
        use_thinking=False,
    )

    normalized = guard.inference(
        action=case["action"],
        image=str(image_path),
        use_few_shot=False,
        use_thinking=False,
    )

    print(
        "Official parsed response:",
        evaluated["parsed_response"]["potential_risk"],
    )
    print(
        "Official normalized response:",
        normalized["potential_risk"],
    )

    expected = (
        "risky"
        if case["stub_response"]["potential_risk"] == "unsafe"
        else "benign"
    )

    assert normalized["potential_risk"] == expected

    results.append({
        "scene": case["scene"],
        "image_path": str(image_path),
        "image_sha256": hashlib.sha256(
            image_path.read_bytes()
        ).hexdigest(),
        "image_parts": len(image_parts),
        "official_parsed_risk": (
            evaluated["parsed_response"]["potential_risk"]
        ),
        "official_normalized_risk": (
            normalized["potential_risk"]
        ),
        "model_inference": False,
        "response_source": "synthetic_stub",
    })


# Check behavior on an unparseable response.
invalid = guard.parse_response(
    "INVALID_OUTPUT_WITHOUT_JSON"
)

print("\n=== Invalid output check ===")
print("Parsed potential_risk:", invalid["potential_risk"])

assert invalid["potential_risk"] is None

report = {
    "experiment": "EMBGuard-E2",
    "status": "PASS",
    "test_type": "official_code_interface_smoke",
    "actual_model_inference": False,
    "official_weights_loaded": False,
    "tested": [
        "prepare_messages",
        "multimodal_serialization",
        "evaluate",
        "parse_response",
        "inference",
    ],
    "invalid_output_requires_adapter_defer": True,
    "results": results,
}

OUT.write_text(json.dumps(
    report, indent=2, ensure_ascii=False
))

print("\n=== EMBGUARD-E2 SUMMARY ===")
print("Cases:", len(results))
print("Official interface smoke: PASS")
print("Official model inference: NOT RUN")
print("Saved:", OUT)
print("EMBGUARD-E2 COMPLETED")
