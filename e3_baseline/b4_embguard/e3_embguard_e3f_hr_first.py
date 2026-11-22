import _bootstrap  # Workspace paths and historical cross-script imports.
import io
import json
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

ROOT = _bootstrap.ROOT
MODEL_DIR = ROOT / "external/EMBGuard-2B"
REPO = ROOT / "external/EMBGuard"
DATA = ROOT / "external/EMBGuardTest-v1/data/HR-00000-of-00001.parquet"
OUT = ROOT / "results/E3/06_embguard"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO))
from src.guardrail.prompts.guardrail_prompt import (
    GUARDRAIL_SYSTEM_PROMPT,
    GUARDRAIL_USER_PROMPT,
    get_few_shot_messages,
)

row = next(pq.ParquetFile(DATA).iter_batches(batch_size=1)).to_pylist()[0]
assert row["Risk"] == "O"

image_bytes = row["image"]["bytes"]
assert image_bytes
image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

print("Sample ID:", row["ID"], flush=True)
print("Original image dimensions:", image.size, flush=True)
print("Action:", row["Action"], flush=True)
print("Ground Truth:", row["Risk"], row["Risk Type"], flush=True)

processor = AutoProcessor.from_pretrained(
    str(MODEL_DIR),
    local_files_only=True,
    use_fast=False,
)

messages = [{"role": "system", "content": GUARDRAIL_SYSTEM_PROMPT}]
messages.extend(get_few_shot_messages())
messages.append({
    "role": "user",
    "content": [
        {"type": "text", "text": GUARDRAIL_USER_PROMPT.format(action=row["Action"])},
        {"type": "image", "image": image},
    ],
})

text = processor.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True
)
inputs = processor(
    text=[text], images=[image],
    padding=True, return_tensors="pt",
)

print("Input tokens:", inputs["input_ids"].shape[1], flush=True)
print("Pixel values shape:", list(inputs["pixel_values"].shape), flush=True)

# Stop before allocating the full model if the native image
# would create an unusually large visual sequence.
visual_patches = inputs["pixel_values"].shape[0]
if visual_patches > 4096:
    raise RuntimeError(
        f"Visual input unusually large: {visual_patches} patches. "
        "Review original resolution and processor settings."
    )

torch.set_num_threads(6)
torch.set_num_interop_threads(2)

print("Loading official EMBGuard-2B...", flush=True)
t0 = time.monotonic()
model = Qwen3VLForConditionalGeneration.from_pretrained(
    str(MODEL_DIR),
    local_files_only=True,
    dtype=torch.float32,
    attn_implementation="eager",
    low_cpu_mem_usage=True,
)
model.eval()
load_sec = time.monotonic() - t0
print("Model loaded:", round(load_sec, 3), "s", flush=True)

t1 = time.monotonic()
with torch.inference_mode():
    output = model.generate(
        **inputs,
        max_new_tokens=128,
        do_sample=False,
        use_cache=True,
    )
infer_sec = time.monotonic() - t1

generated = output[:, inputs["input_ids"].shape[1]:]
raw = processor.batch_decode(
    generated, skip_special_tokens=True
)[0].strip()

import re
match = re.search(r'\{[^{}]*"potential_risk"[^{}]*\}', raw, re.S)
parsed = None
if match:
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

pred = str((parsed or {}).get("potential_risk", "")).lower()
expected = "unsafe"

report = {
    "dataset": "EMBGuard/EMBGuardTest",
    "dataset_revision": "48f2eb559b669dd900328001e4771478bababe4c",
    "sample_id": row["ID"],
    "scenario": "HR",
    "action": row["Action"],
    "image_dimensions": list(image.size),
    "ground_truth": expected,
    "ground_truth_risk_type": row["Risk Type"],
    "prediction": pred,
    "raw_response": raw,
    "parsed_response": parsed,
    "binary_correct": pred == expected if pred in ("safe", "unsafe") else None,
    "risk_type_correct": (
        parsed.get("risk_type") == row["Risk Type"]
        if parsed else None
    ),
    "load_seconds": round(load_sec, 3),
    "infer_seconds": round(infer_sec, 3),
}
out_file = OUT / "e3f_hr_first_cpu.json"
out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

print("\n=== RAW RESPONSE ===")
print(raw)
print("\n=== GROUND TRUTH ===")
print(expected, "|", row["Risk Type"])
print("\n=== RESULT ===")
print("Prediction:", pred)
print("Binary correct:", report["binary_correct"])
print("Risk type correct:", report["risk_type_correct"])
print("Inference seconds:", report["infer_seconds"])
print("Saved:", out_file)
print("EMBGUARD E3F HR FIRST INFERENCE COMPLETE")
