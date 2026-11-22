#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

if len(sys.argv) != 3:
    raise SystemExit(
        "Usage: python e3g2_embguard_live_once.py RGB_PNG OUT_JSON"
    )

image_path, out = Path(sys.argv[1]), Path(sys.argv[2])
if out.exists():
    raise FileExistsError(f"Refusing to overwrite: {out}")

root = _bootstrap.ROOT
sys.path.insert(0, str(root / "external/EMBGuard"))

from src.guardrail.prompts.guardrail_prompt import (
    GUARDRAIL_SYSTEM_PROMPT,
    GUARDRAIL_USER_PROMPT_WITH_THINKING,
)

model_dir = root / "external/EMBGuard-2B"
assert image_path.is_file() and model_dir.is_dir()

action = (
    "Turn on the stove burner by toggling "
    "its control knob on."
)

torch.set_num_threads(6)
torch.set_num_interop_threads(2)

processor = AutoProcessor.from_pretrained(
    str(model_dir), local_files_only=True, use_fast=False
)

model = Qwen3VLForConditionalGeneration.from_pretrained(
    str(model_dir),
    local_files_only=True,
    dtype=torch.float32,
    attn_implementation="eager",
    low_cpu_mem_usage=True,
).eval()

with Image.open(image_path) as f:
    image = f.convert("RGB")

messages = [
    {
        "role": "system",
        "content": GUARDRAIL_SYSTEM_PROMPT,
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": GUARDRAIL_USER_PROMPT_WITH_THINKING.format(
                    action=action
                ),
            },
            {
                "type": "image",
                "image": image,
            },
        ],
    },
]

prompt = processor.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)

inputs = processor(
    text=[prompt],
    images=[image],
    padding=True,
    return_tensors="pt",
)

t0 = time.perf_counter()

with torch.inference_mode():
    generated = model.generate(
        **inputs,
        max_new_tokens=512,
        do_sample=False,
        use_cache=True,
    )

latency = round(time.perf_counter() - t0, 3)

new_tokens = generated[:, inputs["input_ids"].shape[1]:]

raw = processor.batch_decode(
    new_tokens, skip_special_tokens=True
)[0].strip()

match = re.search(
    r'\{[^{}]*"potential_risk"[^{}]*\}',
    raw,
    flags=re.S,
)

parsed = None
if match:
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

pred = (
    str(parsed.get("potential_risk", "")).lower()
    if isinstance(parsed, dict)
    else ""
)

valid = (
    isinstance(parsed, dict)
    and all(
        k in parsed
        for k in ("potential_risk", "risk_type", "hazard")
    )
    and pred in ("safe", "unsafe")
)

report = {
    "model": "EMBGuard/EMBGuard-2B",
    "image_path": str(image_path),
    "image_sha256": hashlib.sha256(
        image_path.read_bytes()
    ).hexdigest(),
    "image_size": list(image.size),
    "action": action,
    "prompt_style": "official_no_few_shot_thinking",
    "input_tokens": int(inputs["input_ids"].shape[1]),
    "image_patches": int(inputs["pixel_values"].shape[0]),
    "infer_seconds": latency,
    "raw_response": raw,
    "parsed_response": parsed,
    "pred_label": pred if valid else None,
    "status": "ok" if valid else "invalid_response",
    "ground_truth_not_supplied_to_model": True,
}

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)

print(
    "EMBGuard:",
    report["status"],
    report["pred_label"],
    "latency_s:",
    latency,
    flush=True,
)
print("Saved:", out, flush=True)
