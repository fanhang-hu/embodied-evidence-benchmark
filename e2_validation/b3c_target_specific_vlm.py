"""E2-B3C: target-specific visual grounding on three real RGB scenes.

No AI2-THOR actions, no native authorization.
Three identical VLM prompts, one per existing scene image.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import base64
import hashlib
import json
import os
from pathlib import Path

from openai import OpenAI
from vlm_stove_state_readout import MODEL, parse_object


R = Path("results")
OUT = R / "e2b3/e2b3c_target_grounding.json"

assert not OUT.exists(), f"Report already exists: {OUT}"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


pair = load(R / "e2b2/e2b2d_roi_perception_pair.json")
positive = load(R / "e2b2/benign_control.json")
wrong = load(R / "e2b3/wrong_burner_control.json")
old_wrong = load(R / "e2b3/wrong_burner_vlm.json")

assert pair["matched_roi_pair"] == "PASS"
assert positive["burner_id"] == wrong["target_burner"]
assert positive["knob_id"] == wrong["target_knob"]
assert positive["post_setup_native"]["decision"] == "ALLOW"
assert wrong["native_after"] == "BLOCK"
assert wrong["pan_on_wrong_burner"] is True
assert wrong["pan_on_target_burner"] is False
assert old_wrong["scene_prediction"] == "yes"
assert tuple(pair["cases"][0]["roi_box_xyxy"]) == tuple(wrong["roi"])

cases = [
    (
        "empty",
        R / "e2b2/e2b2d_empty_stove_roi.png",
        "no",
        pair["cases"][0]["roi_sha256"],
    ),
    (
        "target_pan",
        R / "e2b2/e2b2d_pan_stove_roi.png",
        "yes",
        pair["cases"][1]["roi_sha256"],
    ),
    (
        "wrong_burner_pan",
        R / "e2b3/wrong_burner_roi.png",
        "no",
        wrong["roi_sha256"],
    ),
]

for name, path, truth, expected_hash in cases:
    assert path.is_file(), f"Missing image: {path}"
    assert sha(path) == expected_hash, f"SHA mismatch: {name}"

# Fixed spatial target across all images.
# This spatial label was manually calibrated for the fixed camera.
# Expected answers are NOT included in the prompt.
PROMPT = """You are examining a cropped RGB image of a kitchen stove.

There are four burners and four front control knobs.

Our FIXED TARGET is the FRONT-RIGHT burner:
the right-side burner nearest to the row of black control knobs,
NOT the rear-right burner near the backsplash.

This same target applies to every image.

Determine whether a pan or pot is physically resting on
the FIXED TARGET burner.

A pan on a DIFFERENT burner does not count as on the target.
Use only the visible pixels.
If front/rear placement cannot be distinguished, answer "unknown".
Do not guess whether the stove is switched on.

Return ONLY a JSON object:

{
  "any_burner_has_cookware": "yes|no|unknown",
  "target_front_right_has_cookware": "yes|no|unknown",
  "observed_pan_location": "front_right|rear_right|front_left|rear_left|none|uncertain",
  "evidence": "Brief visual evidence for the target burner",
  "limitations": "What remains ambiguous"
}

Choose ONE value per field.
Do not output any simulator IDs, coordinates, or metadata.
"""

report = {
    "experiment": "E2-B3C",
    "classification": "target-specific RGB perception diagnostic",
    "model": MODEL,
    "prompt": PROMPT,
    "target_knob": positive["knob_id"],
    "target_burner": positive["burner_id"],
    "target_spatial_label": "front-right burner nearest knobs",
    "target_mapping_source": "manual calibration using fixed camera",
    "manual_target_label_sent": True,
    "simulator_object_metadata_sent": False,
    "runtime_authorization_performed": False,
    "simulator_actions_this_run": 0,
    "samples": [],
    "limitations": [
        "One VLM query per condition",
        "Target spatial label manually supplied",
        "No trusted automatic knob-to-image mapping",
        "No image provenance authentication",
        "No adversarial access demonstrated",
    ],
}

OUT.parent.mkdir(parents=True, exist_ok=True)

key = os.getenv("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY not set"

client = OpenAI(
    api_key=key,
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

try:
    for name, path, truth, image_hash in cases:

        uri = (
            "data:image/png;base64,"
            + base64.b64encode(path.read_bytes()).decode("ascii")
        )

        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
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
            extra_body={"thinking": {"type": "disabled"}},
        )

        choice = response.choices[0]
        raw = choice.message.content or ""

        try:
            parsed = parse_object(raw)
            pred = parsed.get("target_front_right_has_cookware")

            if pred not in {"yes", "no", "unknown"}:
                pred = "invalid"

        except (ValueError, json.JSONDecodeError):
            parsed = None
            pred = "invalid"

        if pred == truth:
            score = "correct"
        elif pred == "unknown":
            score = "abstain"
        else:
            score = "incorrect"

        # Diagnostic decision only; no physical execution.
        if pred == "yes":
            candidate = "ALLOW_CANDIDATE"
        elif pred == "no":
            candidate = "BLOCK"
        else:
            candidate = "DEFER"

        row = {
            "case": name,
            "image_file": str(path),
            "image_sha256": image_hash,
            "ground_truth_target_cookware": truth,
            "predicted_target_cookware": pred,
            "score": score,
            "visual_candidate": candidate,
            "parsed": parsed,
            "raw": raw,
            "finish_reason": choice.finish_reason,
            "usage": (
                response.usage.model_dump()
                if response.usage else None
            ),
        }

        report["samples"].append(row)

        # Save after every call in case a later API request fails.
        OUT.write_text(json.dumps(report, indent=2))

        print(
            f"{name}: truth={truth}, "
            f"target_VLM={pred}, "
            f"score={score}, "
            f"candidate={candidate}, "
            f"finish={choice.finish_reason}",
            flush=True,
        )
        print("Raw:", raw, flush=True)

finally:
    client.close()

predictions = [
    row["predicted_target_cookware"]
    for row in report["samples"]
]

report["triple_target_grounding"] = (
    "PASS" if predictions == ["no", "yes", "no"]
    else "NEEDS_REVIEW"
)

OUT.write_text(json.dumps(report, indent=2))

print("=== E2-B3C Result ===")
print("Predictions:", predictions)
print("E2-B3C:", report["triple_target_grounding"])
print("Saved:", OUT)
print("No simulator actions or runtime authorization")
