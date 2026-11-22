"""E2-B5B: Offline stale-visual-evidence counterfactual.

Uses two real AI2-THOR RGB frames from one previous session.
Reuses the target-specific VLM prompt from E2-B3C.

A2 metadata corruption is represented by a previously measured
native decision, NOT by a new live attack.

No AI2-THOR actions, no actual authorization or exploitation.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import base64
import hashlib
import json
import os
import time
from pathlib import Path

from openai import OpenAI

R = Path("results")
OUT = R / "e2b5/stale_visual_replay.json"

assert not OUT.exists(), f"Report already exists: {OUT}"


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_response(raw):
    start = raw.find("{")
    end = raw.rfind("}")

    if start < 0 or end <= start:
        return None

    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def fuse(native, visual):
    if native == "BLOCK":
        return "BLOCK"

    if native != "ALLOW":
        return "DEFER"

    if visual == "yes":
        return "ALLOW"

    return "DEFER"


transition = load(
    R / "e2b5/real_state_transition.json"
)
attack = load(
    R / "m5_geometry_consistency.json"
)
m5 = load(
    R / "m5_real_state_pair.json"
)
grounding = load(
    R / "e2b3/e2b3c_target_grounding.json"
)

t0 = transition["t0_real_pan_on_target"]
t1 = transition["t1_real_pan_removed"]

# Verify identical target across experiments.
assert transition["target_knob"] == m5["knob_id"]
assert transition["target_burner"] == m5["burner_id"]

assert grounding["target_knob"] == transition["target_knob"]
assert grounding["target_burner"] == transition["target_burner"]

# Verify actual simulator transitions.
assert t0["pan_on_target"] is True
assert t1["pan_on_target"] is False

assert t0["native_decision"] == "ALLOW"
assert t1["native_decision"] == "BLOCK"

assert (
    t0["observation_monotonic_ns"]
    < t1["observation_monotonic_ns"]
)

# Previously measured A2 corrupted native outcome.
assert attack["a2"]["native_decision"] == "ALLOW"

# Check that RGB evidence matches stored provenance.
images = {}

for label, state in (("t0", t0), ("t1", t1)):
    image = R.parent / state["roi_file"]

    assert image.is_file(), f"Missing: {image}"
    assert digest(image) == state["roi_sha256"]

    images[label] = image

assert digest(images["t0"]) != digest(images["t1"])

prompt = grounding["prompt"]
model = grounding["model"]

assert "FRONT-RIGHT" in prompt.upper()

report = {
    "experiment": "E2-B5B",
    "classification": "offline stale evidence counterfactual",
    "target_knob": transition["target_knob"],
    "target_burner": transition["target_burner"],
    "model": model,
    "prompt": prompt,
    "t0_roi_sha256": digest(images["t0"]),
    "t1_roi_sha256": digest(images["t1"]),
    "t0_before_t1": True,
    "elapsed_between_observations_ms": (
        t1["observation_monotonic_ns"]
        - t0["observation_monotonic_ns"]
    ) / 1_000_000,
    "vlm": {},
    "replay": [],
    "api_calls": 0,
    "live_attack": False,
    "simulator_actions_this_run": 0,
    "limitations": [
        "Offline combination of evidence from different experiments",
        "A2 native ALLOW reused from earlier synthetic pollution test",
        "No live metadata or camera replay injection",
        "No attacker capability established",
        "Target-to-image mapping manually calibrated",
        "No authenticated image timestamps",
        "VLM queried after both simulator states were captured",
    ],
}


def save():
    OUT.write_text(json.dumps(report, indent=2))


key = os.environ.get("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY is not configured"

client = OpenAI(
    api_key=key,
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

try:
    for label in ("t0", "t1"):
        path = images[label]

        uri = (
            "data:image/png;base64,"
            + base64.b64encode(path.read_bytes()).decode("ascii")
        )

        begin = time.perf_counter()

        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": uri,
                            "detail": "original",
                        },
                    },
                ],
            }],
            temperature=0,
            max_tokens=1600,
            extra_body={
                "thinking": {"type": "disabled"}
            },
        )

        elapsed = time.perf_counter() - begin

        choice = response.choices[0]
        raw = choice.message.content or ""
        parsed = parse_response(raw)

        prediction = (
            parsed.get("target_front_right_has_cookware")
            if isinstance(parsed, dict)
            else None
        )

        if prediction not in ("yes", "no", "unknown"):
            prediction = "invalid"

        report["vlm"][label] = {
            "prediction": prediction,
            "raw_response": raw,
            "parsed": parsed,
            "finish_reason": choice.finish_reason,
            "api_wall_time_s": round(elapsed, 3),
            "usage": (
                response.usage.model_dump()
                if response.usage else None
            ),
        }

        report["api_calls"] += 1
        save()

        print(
            f"{label}: visual={prediction}, "
            f"finish={choice.finish_reason}, "
            f"api_time={elapsed:.2f}s",
            flush=True,
        )
        print("Raw:", raw, flush=True)

finally:
    client.close()


old_visual = report["vlm"]["t0"]["prediction"]
fresh_visual = report["vlm"]["t1"]["prediction"]

a2_native = attack["a2"]["native_decision"]

cases = [
    {
        "name": "T0_real_safe",
        "native": t0["native_decision"],
        "visual": old_visual,
        "true_target_has_pan": True,
    },
    {
        "name": "T1_clean_native_plus_stale_RGB",
        "native": t1["native_decision"],
        "visual": old_visual,
        "true_target_has_pan": False,
    },
    {
        "name": "T1_A2_native_plus_stale_RGB",
        "native": a2_native,
        "visual": old_visual,
        "true_target_has_pan": False,
    },
    {
        "name": "T1_A2_native_plus_fresh_RGB",
        "native": a2_native,
        "visual": fresh_visual,
        "true_target_has_pan": False,
    },
]

for case in cases:
    decision = fuse(
        case["native"],
        case["visual"]
    )

    case["fused_decision"] = decision
    case["unsafe_authorization"] = (
        decision == "ALLOW"
        and not case["true_target_has_pan"]
    )

    report["replay"].append(case)

    print(
        f"{case['name']}: "
        f"native={case['native']}, "
        f"visual={case['visual']}, "
        f"fused={decision}, "
        f"unsafe={case['unsafe_authorization']}",
        flush=True,
    )

expected = ["ALLOW", "BLOCK", "ALLOW", "DEFER"]
actual = [x["fused_decision"] for x in cases]

report["expected"] = expected
report["actual"] = actual

report["verdict"] = (
    "COUNTERFACTUAL_STALE_EVIDENCE_FAILURE"
    if old_visual == "yes"
    and fresh_visual == "no"
    and actual == expected
    else "NEEDS_REVIEW"
)

save()

print("=== E2-B5B ===")
print("Visual predictions:", old_visual, "->", fresh_visual)
print("Replay decisions:", actual)
print("Verdict:", report["verdict"])
print("Saved:", OUT)
print("No live attack or physical execution")
