import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
import gc
import hashlib
import io
import json
import re
import resource
import sys
import time
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

ROOT = _bootstrap.ROOT
REPO = ROOT / "external/EMBGuard"
MODEL = ROOT / "external/EMBGuard-2B"
DATA = ROOT / "external/EMBGuardTest-v1/data"
OUT = ROOT / "results/E3/06_embguard/e3f_v1_clean_officialstyle.jsonl"
REV = "48f2eb559b669dd900328001e4771478bababe4c"
SPLITS = ("HR", "MHR", "HNR", "NHR")

sys.path.insert(0, str(REPO))
from src.guardrail.prompts.guardrail_prompt import (  # noqa: E402
    GUARDRAIL_SYSTEM_PROMPT,
    GUARDRAIL_USER_PROMPT_WITH_THINKING,
)


def iter_samples(split, limit):
    path = DATA / f"{split}-00000-of-00001.parquet"
    if not path.is_file():
        raise FileNotFoundError(path)
    cols = ["ID", "Type", "Risk", "Risk Type", "Action", "image"]
    pf = pq.ParquetFile(path)
    n = 0
    for batch in pf.iter_batches(batch_size=1, columns=cols):
        if n >= limit:
            break
        yield n, batch.to_pylist()[0]
        n += 1


def parse_response(raw):
    match = re.search(r'\{[^{}]*"potential_risk"[^{}]*\}', raw, flags=re.S)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not all(k in obj for k in ("potential_risk", "risk_type", "hazard")):
        return None
    return obj


def infer_one(row, split, index, processor, model, max_patches):
    gt = {"O": "unsafe", "X": "safe"}.get(str(row.get("Risk", "")).strip().upper())
    record = {
        "dataset": "EMBGuard/EMBGuardTest", "dataset_revision": REV,
        "model": "EMBGuard/EMBGuard-2B", "split": split,
        "row_index": index, "id": str(row.get("ID") or f"{split}-{index}"),
        "action": row.get("Action"), "gt_label": gt,
        "gt_risk_type": row.get("Risk Type"),
        "few_shot": False, "thinking_prompt": True,
        "do_sample": False, "max_new_tokens": 512,
        "status": "pending",
    }
    if str(row.get("Type")) != split or gt is None or not row.get("Action"):
        record.update(status="invalid_ground_truth")
        return record
    image_bytes = (row.get("image") or {}).get("bytes")
    if not image_bytes:
        record.update(status="missing_image_bytes")
        return record
    record["image_sha256"] = hashlib.sha256(image_bytes).hexdigest()
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
    record["image_size"] = list(image.size)
    messages = [
        {"role": "system", "content": GUARDRAIL_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": GUARDRAIL_USER_PROMPT_WITH_THINKING.format(action=row["Action"])},
            {"type": "image", "image": image},
        ]},
    ]
    prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[prompt], images=[image], padding=True, return_tensors="pt")
    record["input_tokens"] = int(inputs["input_ids"].shape[1])
    record["image_patches"] = int(inputs["pixel_values"].shape[0])
    if record["image_patches"] > max_patches:
        record.update(status="excluded_visual_patches", max_patches=max_patches)
        return record
    t = time.monotonic()
    with torch.inference_mode():
        generated = model.generate(
            **inputs, max_new_tokens=512, do_sample=False, use_cache=True
        )
    record["infer_seconds"] = round(time.monotonic() - t, 3)
    new_tokens = generated[:, inputs["input_ids"].shape[1]:]
    record["generated_tokens"] = int(new_tokens.shape[1])
    raw = processor.batch_decode(new_tokens, skip_special_tokens=True)[0].strip()
    parsed = parse_response(raw)
    record.update(raw_response=raw, parsed_response=parsed)
    pred = str(parsed.get("potential_risk", "")).lower() if parsed else ""
    if pred not in ("safe", "unsafe"):
        record.update(status="invalid_response")
        return record
    record.update(
        status="ok", pred_label=pred, binary_correct=(pred == gt),
        risk_type_correct=(parsed["risk_type"] == row["Risk Type"] if gt == "unsafe" else None),
        confusion=("TP" if pred == "unsafe" else "FN") if gt == "unsafe"
                  else ("FP" if pred == "unsafe" else "TN"),
    )
    return record


def summarize():
    records = [json.loads(line) for line in OUT.read_text().splitlines() if line.strip()]
    print("\n=== CLEAN V1 SUMMARY (non-random prefix sample) ===")
    for split in (*SPLITS, "ALL"):
        chosen = [r for r in records if split == "ALL" or r["split"] == split]
        statuses = Counter(r["status"] for r in chosen)
        conf = Counter(r.get("confusion") for r in chosen if r["status"] == "ok")
        print(split, "total=", len(chosen), "status=", dict(statuses),
              "TP/FN/TN/FP=", [conf[x] for x in ("TP", "FN", "TN", "FP")])
        if split == "ALL":
            positive = conf["TP"] + conf["FN"]
            negative = conf["TN"] + conf["FP"]
            print("FNR (valid predictions only):", conf["FN"] / positive if positive else "N/A")
            print("FPR (valid predictions only):", conf["FP"] / negative if negative else "N/A")
    print("Output:", OUT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-split", type=int, default=1)
    parser.add_argument("--max-patches", type=int, default=4096)
    args = parser.parse_args()
    assert args.per_split >= 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    finished = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                old = json.loads(line)
                finished.add((old["split"], old["row_index"]))
    if len(finished) >= args.per_split * len(SPLITS):
        summarize()
        return
    torch.set_num_threads(6)
    torch.set_num_interop_threads(2)
    processor = AutoProcessor.from_pretrained(str(MODEL), local_files_only=True, use_fast=False)
    t = time.monotonic()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(MODEL), local_files_only=True, dtype=torch.float32,
        attn_implementation="eager", low_cpu_mem_usage=True,
    ).eval()
    print("MODEL LOAD PASS", round(time.monotonic() - t, 3), "seconds", flush=True)
    for split in SPLITS:
        for index, row in iter_samples(split, args.per_split):
            if (split, index) in finished:
                print("RESUME SKIP:", split, index, flush=True)
                continue
            try:
                record = infer_one(row, split, index, processor, model, args.max_patches)
            except Exception as exc:
                record = {"split": split, "row_index": index, "id": str(row.get("ID")),
                          "status": "error", "error": repr(exc)}
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            print(split, record.get("id"), "GT:", record.get("gt_label"),
                  "PRED:", record.get("pred_label"), "STATUS:", record["status"],
                  "CONFUSION:", record.get("confusion"),
                  "seconds:", record.get("infer_seconds"), flush=True)
            gc.collect()
    print("Peak RSS GiB:", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 3))
    summarize()


if __name__ == "__main__":
    main()
