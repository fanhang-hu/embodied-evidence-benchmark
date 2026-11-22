#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
from PIL import Image
import e3_hdguard_e5d_branch_ablation as e5d

OUT = Path(
    "results/E3/05_hdguard/e5d2_forced_slow_repeat"
)
TIMES = (3.4, 3.6, 3.8, 4.0)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def atomic_json(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(
        obj, ensure_ascii=False, indent=2, default=str
    ))
    temp.replace(path)


def parse_verdict(raw):
    if not isinstance(raw, str):
        return None

    matches = re.findall(
        r'(?im)^\s*(?:\*\*)?VERDICT(?:\*\*)?\s*[:：]\s*'
        r'(?:\*\*)?(DANGER|SAFE)\b',
        raw
    )
    matches = [s.upper() for s in matches]

    return matches[0] if len(matches) == 1 else None


def frames_for_video(path):
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")

    frames = []

    try:
        for sec in TIMES:
            cap.set(cv2.CAP_PROP_POS_MSEC, 1000 * sec)
            ok, bgr = cap.read()

            if not ok:
                raise RuntimeError(
                    f"Cannot decode video at {sec}s"
                )

            frames.append(Image.fromarray(
                cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            ))
    finally:
        cap.release()

    masked = [e5d.black(frame) for frame in frames]

    return {
        "clean": frames,
        "masked": masked,
    }


def summary(pairs):
    records = []

    for i in range(1, pairs + 1):
        results = {}

        for condition in ("clean", "masked"):
            path = OUT / f"pair_{i:02d}_{condition}.json"

            if path.exists():
                results[condition] = json.loads(
                    path.read_text()
                )

        if not results:
            continue

        c = results.get("clean")
        m = results.get("masked")

        eligible = bool(
            c and m and c["valid"] and m["valid"]
        )

        flip = (
            eligible
            and c["verdict"] == "DANGER"
            and m["verdict"] == "SAFE"
        )

        records.append({
            "pair": i,
            "complete": bool(c and m),
            "eligible": eligible,
            "clean": c["verdict"] if c else None,
            "masked": m["verdict"] if m else None,
            "clean_seconds": (
                c["wall_seconds"] if c else None
            ),
            "masked_seconds": (
                m["wall_seconds"] if m else None
            ),
            "danger_to_safe": flip,
        })

    d = {
        "experiment": "HD-Guard E5-D2",
        "component_only_not_native_scheduler": True,
        "pairs_requested": pairs,
        "pairs_complete": sum(
            x["complete"] for x in records
        ),
        "eligible_pairs": sum(
            x["eligible"] for x in records
        ),
        "danger_to_safe_pairs": sum(
            x["danger_to_safe"] for x in records
        ),
        "clean_danger": sum(
            x["clean"] == "DANGER" for x in records
        ),
        "masked_safe": sum(
            x["masked"] == "SAFE" for x in records
        ),
        "timestamps": TIMES,
        "records": records,
    }

    atomic_json(OUT / "summary.json", d)

    print("\n=== E5-D2 SUMMARY ===", flush=True)

    for x in records:
        print(
            f"Pair {x['pair']:02d}: "
            f"clean={x['clean']} "
            f"masked={x['masked']} "
            f"eligible={x['eligible']} "
            f"flip={x['danger_to_safe']}",
            flush=True,
        )

    print(
        f"Complete={d['pairs_complete']} "
        f"Valid={d['eligible_pairs']} "
        f"Danger->Safe={d['danger_to_safe_pairs']}",
        flush=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=3)
    args = ap.parse_args()

    if not 1 <= args.pairs <= 5:
        ap.error("--pairs must be between 1 and 5")

    if not (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    ):
        ap.error("DeepSeek API key not configured")

    # Reuse E5-D and E5-B validated setup.
    env, e5b_sha = e5d.load_original()

    assert env["MODEL"] == "deepseek-flash"

    video_path = Path(env["video"]["path"])
    frames = frames_for_video(video_path)

    image_hashes = {
        case: [e5d.sha(x) for x in ff]
        for case, ff in frames.items()
    }

    if any(
        a == b
        for a, b in zip(
            image_hashes["clean"],
            image_hashes["masked"],
        )
    ):
        raise RuntimeError(
            "Masked frame identical to clean frame"
        )

    OUT.mkdir(parents=True, exist_ok=True)

    fingerprint = {
        "model": env["MODEL"],
        "e5b_sha256": e5b_sha,
        "e5d_sha256": digest(
            "e3_baseline/b5_hdguard/e3_hdguard_e5d_branch_ablation.py"
        ),
        "official_source_sha256": digest(
            env["SOURCE"]
        ),
        "video_sha256": digest(video_path),
        "frame_hashes": image_hashes,
        "timestamps": list(TIMES),
    }

    fingerprint_path = OUT / "fingerprint.json"

    if fingerprint_path.exists():
        old = json.loads(fingerprint_path.read_text())

        if old != fingerprint:
            raise RuntimeError(
                "Input/source changed; refusing to mix results"
            )
    else:
        atomic_json(fingerprint_path, fingerprint)

    print("Model:", env["MODEL"])
    print("Frame hashes:", image_hashes)

    for pair in range(1, args.pairs + 1):
        order = (
            ("clean", "masked")
            if pair % 2
            else ("masked", "clean")
        )

        for condition in order:
            path = (
                OUT / f"pair_{pair:02d}_{condition}.json"
            )

            if path.exists():
                print("Skip existing:", path, flush=True)
                continue

            print(
                f"\n=== Pair {pair:02d}: {condition} ===",
                flush=True,
            )

            slow = env["DeepSeekSlowBrain"]()

            begin = time.perf_counter()
            raw, native_cost = None, None
            error = None

            try:
                raw, native_cost = slow.deep_reason(
                    frames[condition]
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

            elapsed = time.perf_counter() - begin

            verdict = parse_verdict(raw)
            requests = slow.requests

            api_error = bool(
                error
                or len(requests) != 1
                or any(
                    r.get("api_error") for r in requests
                )
            )

            result = {
                "experiment": "E5-D2",
                "pair": pair,
                "condition": condition,
                "model": env["MODEL"],
                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "timestamps": TIMES,
                "frame_hashes": image_hashes[condition],
                "original_slow_method": True,
                "native_scheduler": False,
                "GT_supplied_to_model": False,
                "raw_response": raw,
                "verdict": verdict,
                "native_cost_seconds": native_cost,
                "wall_seconds": round(elapsed, 3),
                "api_error": api_error,
                "exception": error,
                "valid": (
                    verdict in ("DANGER", "SAFE")
                    and not api_error
                ),
                "requests": requests,
            }

            atomic_json(path, result)

            print(
                "Verdict:", verdict,
                "| API error:", api_error,
                "| Wall:", round(elapsed, 3),
                flush=True,
            )

            summary(args.pairs)

            if not result["valid"]:
                raise RuntimeError(
                    f"Invalid Slow result: {path}"
                )

    summary(args.pairs)


if __name__ == "__main__":
    main()
