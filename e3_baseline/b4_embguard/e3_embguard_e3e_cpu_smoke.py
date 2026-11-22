import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
import hashlib
import json
import re
import resource
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import (
    AutoProcessor,
    Qwen3VLForConditionalGeneration,
)

ROOT = _bootstrap.ROOT
MODEL_DIR = ROOT / "external/EMBGuard-2B"
REPO = ROOT / "external/EMBGuard"
IMAGE = ROOT / "smoke_rgb.png"
OUT_DIR = ROOT / "results/E3/06_embguard"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO))

from src.guardrail.prompts.guardrail_prompt import (
    GUARDRAIL_SYSTEM_PROMPT,
    GUARDRAIL_USER_PROMPT,
    get_few_shot_messages,
)

ACTION = "Move forward one step"

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def rss_gib():
    return round(
        resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss / 1024**2,
        3,
    )

def main(step):
    start = time.monotonic()

    assert IMAGE.exists(), IMAGE
    assert (MODEL_DIR / "model.safetensors").exists()

    torch.set_num_threads(6)
    torch.set_num_interop_threads(2)

    processor = AutoProcessor.from_pretrained(
        str(MODEL_DIR),
        local_files_only=True,
        use_fast=False,
    )

    image = Image.open(IMAGE).convert("RGB")

    messages = [{
        "role": "system",
        "content": GUARDRAIL_SYSTEM_PROMPT,
    }]

    # Match the original EMBGuard default:
    # use_few_shot=True, use_thinking=False
    messages.extend(get_few_shot_messages())

    user_prompt = GUARDRAIL_USER_PROMPT.format(
        action=ACTION
    )

    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image", "image": str(IMAGE)},
        ],
    })

    rendered = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = processor(
        text=[rendered],
        images=[image],
        padding=True,
        return_tensors="pt",
    )

    metadata = {
        "model": str(MODEL_DIR),
        "model_revision":
          "4f9a4f4f7a15a00da836085d8ccb10c6448f23b7",
        "official_prompt": True,
        "few_shot": True,
        "thinking": False,
        "action": ACTION,
        "image": str(IMAGE),
        "image_size": list(image.size),
        "image_sha256": sha256(IMAGE),
        "prompt_file_sha256": sha256(
            REPO / "src/guardrail/prompts/guardrail_prompt.py"
        ),
        "input_tokens": int(inputs["input_ids"].shape[1]),
        "input_shapes": {
            k: list(v.shape)
            for k, v in inputs.items()
            if hasattr(v, "shape")
        },
        "torch": torch.__version__,
    }

    print("=== EMBGUARD E3E ===", flush=True)
    print("Step:", step, flush=True)
    print("Image:", IMAGE, image.size, flush=True)
    print("Action:", ACTION, flush=True)
    print("Input tokens:", metadata["input_tokens"], flush=True)
    print("Input tensor shapes:", metadata["input_shapes"], flush=True)

    if step == "prepare":
        dest = OUT_DIR / "e3e_prepare.json"
        dest.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        print("EMBGUARD E3E-2 PREPARE PASS", flush=True)
        print("Saved:", dest, flush=True)
        return

    print("Loading official 2B model on CPU...", flush=True)
    load_start = time.monotonic()

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(MODEL_DIR),
        local_files_only=True,
        torch_dtype=torch.float32,
        attn_implementation="eager",
        low_cpu_mem_usage=True,
    )

    model.eval()
    load_seconds = time.monotonic() - load_start

    print(
        "MODEL LOAD PASS",
        "seconds=", round(load_seconds, 3),
        "peak_RSS_GiB=", rss_gib(),
        flush=True,
    )

    infer_start = time.monotonic()

    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            use_cache=True,
        )

    infer_seconds = time.monotonic() - infer_start

    new_tokens = generated[
        :, inputs["input_ids"].shape[1]:
    ]

    raw = processor.batch_decode(
        new_tokens,
        skip_special_tokens=True,
    )[0].strip()

    match = re.search(
        r'\{[^{}]*"potential_risk"[^{}]*\}',
        raw,
        re.DOTALL,
    )

    parsed = None
    if match:
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    report = {
        **metadata,
        "load_seconds": round(load_seconds, 3),
        "infer_seconds": round(infer_seconds, 3),
        "total_seconds": round(
            time.monotonic() - start, 3
        ),
        "generated_tokens": int(new_tokens.shape[1]),
        "peak_rss_gib": rss_gib(),
        "raw_response": raw,
        "parsed_response": parsed,
    }

    dest = OUT_DIR / "e3e_cpu_smoke.json"
    dest.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n=== RAW RESPONSE ===", flush=True)
    print(raw, flush=True)

    print("\n=== PARSED RESPONSE ===", flush=True)
    print(parsed, flush=True)

    print("\n=== PERFORMANCE ===", flush=True)
    print("Load seconds:", report["load_seconds"], flush=True)
    print("Inference seconds:", report["infer_seconds"], flush=True)
    print("Peak RSS GiB:", report["peak_rss_gib"], flush=True)
    print("Saved:", dest, flush=True)

    if parsed is not None and all(
        key in parsed
        for key in ("potential_risk", "risk_type", "hazard")
    ):
        print("EMBGUARD E3E-3 CPU INFERENCE PASS", flush=True)
    else:
        print(
            "EMBGUARD E3E-3 GENERATION COMPLETE "
            "BUT STRUCTURED OUTPUT NOT VERIFIED",
            flush=True,
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--step",
        choices=["prepare", "infer"],
        required=True,
    )
    args = parser.parse_args()
    main(args.step)
