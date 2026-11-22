import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = _bootstrap.ROOT

BASE = (
    ROOT
    / "results/E3/07_percepttwin/e2c_rgb_observability"
)

a_path = BASE / "rgb_pan_countertop.png"
b_path = BASE / "rgb_pan_burner.png"

assert a_path.is_file()
assert b_path.is_file()

a = Image.open(a_path).convert("RGB")
b = Image.open(b_path).convert("RGB")

assert a.size == b.size

aa = np.asarray(a).astype(np.int16)
bb = np.asarray(b).astype(np.int16)

diff = np.abs(aa - bb)

# Significant RGB changes.
strength = diff.max(axis=2)
mask = strength >= 24

ys, xs = np.where(mask)

assert len(xs) > 30, "Not enough changed pixels"

w, h = a.size

# Discard isolated extreme pixels when locating
# the principal area of visual change.
x0 = int(np.quantile(xs, 0.01))
x1 = int(np.quantile(xs, 0.99)) + 1
y0 = int(np.quantile(ys, 0.01))
y1 = int(np.quantile(ys, 0.99)) + 1

# Add context around the changed region.
margin = 25

cx = (x0 + x1) // 2
cy = (y0 + y1) // 2

crop_w = min(w, max(120, x1 - x0 + 2 * margin))
crop_h = min(h, max(120, y1 - y0 + 2 * margin))

left = max(0, min(w - crop_w, cx - crop_w // 2))
top = max(0, min(h - crop_h, cy - crop_h // 2))

box = (
    left,
    top,
    left + crop_w,
    top + crop_h
)

print("Original image:", a.size)
print("Changed pixels, threshold 24:", len(xs))
print("Changed fraction:", round(float(mask.mean()), 6))
print("Main difference ROI:", box)

# Display the same crop for both states.
scale = 3

ca = a.crop(box).resize(
    (crop_w * scale, crop_h * scale),
    Image.Resampling.NEAREST
)

cb = b.crop(box).resize(
    (crop_w * scale, crop_h * scale),
    Image.Resampling.NEAREST
)

canvas = Image.new(
    "RGB",
    (crop_w * scale * 2 + 20,
     crop_h * scale + 45),
    "white"
)

draw = ImageDraw.Draw(canvas)

draw.text((8, 10), "A: Empty burner", fill="black")
draw.text(
    (crop_w * scale + 18, 10),
    "B: Pan on burner",
    fill="black"
)

canvas.paste(ca, (5, 35))
canvas.paste(cb, (crop_w * scale + 15, 35))

zoom_path = BASE / "rgb_difference_roi_zoom.png"
canvas.save(zoom_path)

# Full-image difference heatmap.
heat = np.clip(strength * 4, 0, 255).astype(np.uint8)

heat_rgb = np.zeros((h, w, 3), dtype=np.uint8)
heat_rgb[:, :, 0] = heat

heat_path = BASE / "rgb_difference_heatmap.png"
Image.fromarray(heat_rgb).save(heat_path)

# Annotated original images.
anno_a = a.copy()
anno_b = b.copy()

for img in (anno_a, anno_b):
    d = ImageDraw.Draw(img)
    d.rectangle(box, outline="red", width=2)

overview = Image.new("RGB", (w * 2 + 20, h + 35), "white")
overview.paste(anno_a, (5, 25))
overview.paste(anno_b, (w + 15, 25))

d = ImageDraw.Draw(overview)
d.text((5, 5), "A: CounterTop", fill="black")
d.text((w + 15, 5), "B: StoveBurner", fill="black")

overview_path = BASE / "rgb_difference_roi_overview.png"
overview.save(overview_path)

report = {
    "experiment": "E2-C3_RGB_visual_diagnostic",
    "input_image_size": [w, h],
    "significant_change_threshold": 24,
    "significant_changed_pixels": int(len(xs)),
    "significant_change_fraction": float(mask.mean()),
    "roi_xyxy": list(map(int, box)),
    "visual_review_required": True,
    "embguard_inference_performed": False,
}

out = BASE / "e2c_rgb_visual_diagnostic.json"
out.write_text(json.dumps(report, indent=2))

print("\n=== E2-C3 RESULTS ===")
print("ROI zoom:", zoom_path)
print("Heatmap:", heat_path)
print("ROI overview:", overview_path)
print("Report:", out)
print("E2-C3 ANALYSIS PASS")
