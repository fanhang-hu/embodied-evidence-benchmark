"""E2-B5C: Audit target-specific visual binding disagreement.

Offline image comparison only.
No VLM/API call, no simulator action, no authorization.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

R = Path("results")
OUT = R / "e2b5"
OUT.mkdir(parents=True, exist_ok=True)


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


transition = load(OUT / "real_state_transition.json")
replay = load(OUT / "stale_visual_replay.json")
grounding = load(
    R / "e2b3/e2b3c_target_grounding.json"
)
wrong = load(
    R / "e2b3/wrong_burner_control.json"
)

assert (
    transition["target_burner"]
    == grounding["target_burner"]
    == wrong["target_burner"]
)

assert (
    transition["target_knob"]
    == grounding["target_knob"]
    == wrong["target_knob"]
)

samples = {
    x["case"]: x for x in grounding["samples"]
}

items = [
    (
        "Earlier TARGET Pan | VLM YES",
        R / "e2b2/e2b2d_pan_stove_roi.png",
        samples["target_pan"]["image_sha256"],
    ),
    (
        "New T0 TARGET Pan | VLM NO",
        R / "e2b5/t0_pan_on_target_roi.png",
        transition["t0_real_pan_on_target"]["roi_sha256"],
    ),
    (
        "WRONG burner Pan | VLM NO",
        R / "e2b3/wrong_burner_roi.png",
        wrong["roi_sha256"],
    ),
    (
        "T1 Pan REMOVED | VLM NO",
        R / "e2b5/t1_pan_removed_roi.png",
        transition["t1_real_pan_removed"]["roi_sha256"],
    ),
]

images = []
details = []

for label, path, expected_hash in items:
    assert path.is_file(), f"Missing image: {path}"
    actual_hash = sha(path)

    assert actual_hash == expected_hash, (
        f"Hash mismatch: {path}"
    )

    with Image.open(path) as im:
        image = im.convert("RGB").copy()

    assert image.size == (600, 400), (
        f"Unexpected ROI dimensions: {path}"
    )

    images.append(image)
    details.append({
        "label": label,
        "path": str(path),
        "sha256": actual_hash,
    })

assert (
    grounding["triple_target_grounding"] == "PASS"
)
assert (
    replay["vlm"]["t0"]["prediction"] == "no"
)
assert (
    transition["t0_real_pan_on_target"]["pan_on_target"]
    is True
)
assert (
    transition["t0_real_pan_on_target"]["native_decision"]
    == "ALLOW"
)


def difference(a, b):
    aa = np.asarray(a, dtype=np.int16)
    bb = np.asarray(b, dtype=np.int16)
    diff = np.abs(aa - bb)

    mean_delta = float(diff.mean())
    changed = float(
        (diff.max(axis=2) >= 30).mean()
    )

    visualization = Image.fromarray(
        np.clip(diff * 3, 0, 255).astype("uint8"),
        "RGB",
    )

    return visualization, {
        "mean_abs_channel_delta": round(mean_delta, 4),
        "changed_pixel_fraction_ge30": round(changed, 6),
    }


diff_old_t0, metric_old_t0 = difference(
    images[0], images[1]
)

diff_t0_wrong, metric_t0_wrong = difference(
    images[1], images[2]
)

panels = [
    (items[0][0], images[0]),
    (items[1][0], images[1]),
    (items[2][0], images[2]),
    ("Earlier TARGET vs T0 | difference", diff_old_t0),
    ("T0 TARGET vs WRONG | difference", diff_t0_wrong),
    (items[3][0], images[3]),
]

W, H = 600, 430
canvas = Image.new(
    "RGB", (W * 3, H * 2), "white"
)
draw = ImageDraw.Draw(canvas)

for i, (label, image) in enumerate(panels):
    x = (i % 3) * W
    y = (i // 3) * H

    draw.text(
        (x + 12, y + 8),
        label,
        fill="black",
    )

    canvas.paste(image, (x, y + 30))

figure_path = OUT / "e2b5c_visual_binding_comparison.png"
canvas.save(figure_path)

report = {
    "experiment": "E2-B5C",
    "classification": "offline image and visual-binding audit",
    "target_burner": transition["target_burner"],
    "target_knob": transition["target_knob"],
    "images": details,
    "earlier_target_vs_new_t0": metric_old_t0,
    "new_t0_vs_wrong_burner": metric_t0_wrong,
    "earlier_target_vlm": (
        samples["target_pan"]["predicted_target_cookware"]
    ),
    "new_t0_vlm": replay["vlm"]["t0"]["prediction"],
    "new_t0_simulator_target_has_pan": True,
    "new_t0_native_safety": "ALLOW",
    "new_t0_vlm_description": (
        replay["vlm"]["t0"]["parsed"] or {}
    ).get("observed_pan_location"),
    "model_calls": 0,
    "simulator_actions": 0,
    "interpretation": (
        "Same target ID, different RGB observations and "
        "different VLM predictions. Image evidence requires "
        "manual examination before assigning a root cause."
    ),
}

output = OUT / "e2b5c_visual_binding_audit.json"
output.write_text(json.dumps(report, indent=2))

print("=== E2-B5C Visual Binding Audit ===")
print("Target burner ID consistent: YES")
print("Target knob ID consistent: YES")
print(
    "Earlier target VLM:",
    report["earlier_target_vlm"],
)
print(
    "New T0 target VLM:",
    report["new_t0_vlm"],
)
print(
    "New T0 reported Pan location:",
    report["new_t0_vlm_description"],
)
print(
    "Earlier TARGET vs new T0:",
    metric_old_t0,
)
print(
    "New T0 vs WRONG burner:",
    metric_t0_wrong,
)
print("Saved comparison:", figure_path)
print("Saved report:", output)
print("E2-B5C AUDIT COMPLETE; MANUAL REVIEW REQUIRED")
