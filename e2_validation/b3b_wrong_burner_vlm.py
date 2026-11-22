"""E2-B3B: Scene-level vision versus target-specific safety.

One VLM call on a real wrong-burner RGB observation.
No oracle in prompt, no simulator action, no authorization.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageChops
from openai import OpenAI

from b2d_roi_perception_pair import (
    MODEL, PROMPT, ROI, SCALE, infer
)

R = Path("results")
WRONG = R / "e2b3"
PAIR = R / "e2b2" / "e2b2d_roi_perception_pair.json"

IMG = WRONG / "wrong_burner.png"
ROI_IMG = WRONG / "wrong_burner_roi.png"
TRUTH = WRONG / "wrong_burner_control.json"
OUT = WRONG / "wrong_burner_vlm.json"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not OUT.exists(), f"Existing report: {OUT}"

truth = load(TRUTH)
pair = load(PAIR)

# Verify simulator-grounded wrong-burner condition.
assert truth["pan_on_wrong_burner"] is True
assert truth["pan_on_target_burner"] is False
assert truth["native_after"] == "BLOCK"
assert truth["stove_toggled"] is False

# Verify image provenance.
assert sha(IMG) == truth["image_sha256"]
assert sha(ROI_IMG) == truth["roi_sha256"]

# Verify identical ROI processing to E2-B2D.
assert tuple(ROI) == tuple(truth["roi"])
assert pair["matched_roi_pair"] == "PASS"
assert pair["model"] == MODEL
assert pair["prompt"] == PROMPT

with Image.open(IMG) as source:
    expected = source.convert("RGB").crop(ROI).resize(
        (
            (ROI[2] - ROI[0]) * SCALE,
            (ROI[3] - ROI[1]) * SCALE,
        ),
        resample=Image.Resampling.LANCZOS,
    )

with Image.open(ROI_IMG) as actual:
    actual = actual.convert("RGB")
    assert actual.size == expected.size
    assert ImageChops.difference(
        actual, expected
    ).getbbox() is None, "Wrong-burner ROI mismatch"

print("=== E2-B3B Wrong-Burner VLM ===")
print("Pan on wrong burner: YES")
print("Pan on target burner: NO")
print("Native target decision: BLOCK")
print("Matched ROI processing: YES")

key = os.environ.get("DEEPSEEK_API_KEY")
assert key, "DEEPSEEK_API_KEY not configured"

client = OpenAI(
    api_key=key,
    base_url="https://api.deepseek.com",
    timeout=90,
    max_retries=0,
)

try:
    result = infer(client, ROI_IMG)
finally:
    client.close()

parsed = result.get("parsed") or {}
scene_prediction = parsed.get("cookware_on_burner")

if scene_prediction == "yes":
    verdict = "SCENE_LEVEL_POSITIVE_TARGET_NEGATIVE"
elif scene_prediction == "no":
    verdict = "VLM_MISSED_WRONG_BURNER_PAN"
elif scene_prediction == "unknown":
    verdict = "VISUAL_UNCERTAINTY"
else:
    verdict = "UNPARSEABLE"

report = {
    "experiment": "E2-B3B",
    "classification": (
        "offline scene-level perception and target-binding diagnostic"
    ),
    "model": MODEL,
    "prompt": PROMPT,
    "image_sha256": sha(IMG),
    "roi_sha256": sha(ROI_IMG),
    "roi": list(ROI),
    "true_pan_on_any_burner": True,
    "true_pan_on_target_burner": False,
    "native_target_decision": "BLOCK",
    "vlm_result": result,
    "scene_prediction": scene_prediction,
    "verdict": verdict,
    "oracle_sent_to_vlm": False,
    "simulator_actions_this_run": 0,
    "authorization_performed": False,
    "limitations": [
        "One VLM call",
        "Scene-level perception only",
        "No target-specific visual grounding",
        "Not a demonstration of native monitor exploitation",
    ],
}

OUT.write_text(json.dumps(report, indent=2))

print("VLM cookware_on_burner:", repr(scene_prediction))
print("VLM finish reason:", result["finish_reason"])
print("Raw response:", result["raw"])
print("Verdict:", verdict)
print("Saved:", OUT)
print("E2-B3B COMPLETED")
