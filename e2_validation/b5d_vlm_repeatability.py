"""E2-B5D: Repeated target-specific VLM inference.

Two independently captured real target-pan images.
Three identical requests per image, interleaved.

No simulator action, no image modification, no runtime authorization.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import base64
import hashlib
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from PIL import Image

R = Path("results")
OUT = R / "e2b5/e2b5d_vlm_repeatability.json"

assert not OUT.exists(), f"Report already exists: {OUT}"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(raw):
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        result = json.loads(raw[start:end + 1])
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


grounding = load(
    R / "e2b3/e2b3c_target_grounding.json"
)
transition = load(
    R / "e2b5/real_state_transition.json"
)
replay = load(
    R / "e2b5/stale_visual_replay.json"
)

old_sample = next(
    x for x in grounding["samples"]
    if x["case"] == "target_pan"
)

new_sample = transition["t0_real_pan_on_target"]

# Confirm the recorded disagreement and identical request setup.
assert old_sample["predicted_target_cookware"] == "yes"
assert replay["vlm"]["t0"]["prediction"] == "no"
assert grounding["model"] == replay["model"]
assert grounding["prompt"] == replay["prompt"]

assert grounding["target_knob"] == transition["target_knob"]
assert grounding["target_burner"] == transition["target_burner"]
assert new_sample["pan_on_target"] is True
assert new_sample["native_decision"] == "ALLOW"

paths = {
    "earlier": Path(old_sample["image_file"]),
    "new_t0": Path(new_sample["roi_file"]),
}
expected_hashes = {
    "earlier": old_sample["image_sha256"],
    "new_t0": new_sample["roi_sha256"],
}

for label, path in paths.items():
    assert path.is_file(), f"Missing: {path}"
    assert sha(path) == expected_hashes[label]
    with Image.open(path) as img:
        assert img.size == (600, 400)

assert expected_hashes["earlier"] != expected_hashes["new_t0"]

# Alternating order reduces, but does not eliminate, time confounding.
order = [
    "earlier",
    "new_t0",
    "new_t0",
    "earlier",
    "earlier",
    "new_t0",
]

uris = {
    label: (
        "data:image/png;base64,"
        + base64.b64encode(path.read_bytes()).decode("ascii")
    )
    for label, path in paths.items()
}

report = {
    "experiment": "E2-B5D",
    "classification": "fixed-image VLM repeatability diagnostic",
    "model": grounding["model"],
    "prompt": grounding["prompt"],
    "request_config": {
        "temperature": 0,
        "max_tokens": 1600,
        "thinking": "disabled",
        "image_detail": "original",
    },
    "image_sha256": expected_hashes,
    "ground_truth_target_has_pan": {
        "earlier": True,
        "new_t0": True,
    },
    "previous_predictions": {
        "earlier": "yes",
        "new_t0": "no",
    },
    "call_order": order,
    "calls": [],
    "simulator_actions": 0,
    "runtime_authorization": False,
    "oracle_metadata_sent": False,
}


def save():
    OUT.write_text(json.dumps(report, indent=2))


key = os.environ.get("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY not set"

client = OpenAI(
    api_key=key,
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

try:
    for i, label in enumerate(order, 1):
        start = time.perf_counter()

        response = client.chat.completions.create(
            model=grounding["model"],
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": grounding["prompt"],
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": uris[label],
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

        elapsed = time.perf_counter() - start
        choice = response.choices[0]
        raw = choice.message.content or ""
        parsed = parse(raw)

        prediction = (
            parsed.get("target_front_right_has_cookware")
            if parsed else None
        )

        if prediction not in ("yes", "no", "unknown"):
            prediction = "invalid"

        item = {
            "call": i,
            "image": label,
            "image_sha256": expected_hashes[label],
            "prediction": prediction,
            "parsed": parsed,
            "raw": raw,
            "finish_reason": choice.finish_reason,
            "elapsed_s": round(elapsed, 3),
            "usage": (
                response.usage.model_dump()
                if response.usage else None
            ),
        }

        report["calls"].append(item)
        save()

        print(
            f"Call {i}/6: image={label}, "
            f"target={prediction}, "
            f"finish={choice.finish_reason}, "
            f"time={elapsed:.2f}s",
            flush=True,
        )

finally:
    client.close()


predictions = {
    label: [
        x["prediction"]
        for x in report["calls"]
        if x["image"] == label
    ]
    for label in paths
}

within_image_disagreement = {
    label: len(set(values)) > 1
    for label, values in predictions.items()
}

report["predictions"] = predictions
report["within_image_disagreement"] = within_image_disagreement

report["verdict"] = (
    "IDENTICAL_IMAGE_OUTPUT_DISAGREEMENT"
    if any(within_image_disagreement.values())
    else "NO_WITHIN_IMAGE_DISAGREEMENT_IN_THREE_REPEATS"
)

report["limitations"] = [
    "Only three repeated calls per image",
    "Two very similar, not identical, captured images",
    "No statistical reliability guarantee",
    "No attacker control over the visual input demonstrated",
    "No end-to-end runtime safety authorization",
]

save()

print("\n=== E2-B5D Result ===")
print("Earlier image:", predictions["earlier"])
print("New T0 image:", predictions["new_t0"])
print("Verdict:", report["verdict"])
print("Saved:", OUT)
print("No simulator actions or runtime authorization")
