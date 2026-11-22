#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from PIL import Image

E5B = Path("e3_baseline/b5_hdguard/e3_hdguard_e5b_deepseek_native.py")
OUT = Path("results/E3/05_hdguard/e5d_branch_ablation")

MASK_FROM = 3.3
START_SECOND = 3.0
MAX_FAST_FRAMES = 6


def sha(frame):
    return hashlib.sha256(frame.tobytes()).hexdigest()


def black(frame):
    if isinstance(frame, Image.Image):
        return Image.new(frame.mode, frame.size, 0)
    result = frame.copy()
    result[...] = 0
    return result


def load_original():
    source = E5B.read_text()
    marker = "\nreport = {"
    assert source.count(marker) == 1

    env = {"__name__": "_e5d_setup_"}

    # Reuse the already validated E5-B setup.
    exec(
        compile(
            source.split(marker, 1)[0],
            str(E5B),
            "exec",
        ),
        env,
    )

    return env, hashlib.sha256(source.encode()).hexdigest()


def run_native(kind, env, source_sha):
    control = {
        "timestamp": None,
        "frames": [],
        "fast": [],
        "slow": [],
    }

    fast_mask = kind in ("fast_only", "shared")
    slow_mask = kind in ("slow_only", "shared")

    BaseFast = env["DeepSeekFastBrain"]
    BaseSlow = env["DeepSeekSlowBrain"]

    class FastProbe(BaseFast):
        def analyze_chunk(self, frame):
            timestamp = control["timestamp"]

            masked = (
                fast_mask
                and timestamp is not None
                and timestamp >= MASK_FROM
            )

            supplied = black(frame) if masked else frame

            result = super().analyze_chunk(supplied)

            control["fast"].append({
                "timestamp": timestamp,
                "masked": masked,
                "original_hash": sha(frame),
                "supplied_hash": sha(supplied),
                "category": result.get("category"),
            })

            return result

    class SlowProbe(BaseSlow):
        def deep_reason(self, frames):
            # Strong all-context contamination.
            # This is a component diagnostic, not
            # a timestamp-aligned attack budget.
            supplied = (
                [black(f) for f in frames]
                if slow_mask else frames
            )

            result = super().deep_reason(supplied)

            control["slow"].append({
                "masked": slow_mask,
                "frame_count": len(frames),
                "original_hashes": [sha(f) for f in frames],
                "supplied_hashes": [sha(f) for f in supplied],
            })

            return result

    # Keep native DualBrainSystem scheduling unchanged.
    env["native_ns"]["FastBrain"] = FastProbe
    env["native_ns"]["SlowBrain"] = SlowProbe

    native_path = OUT / f"{kind}_native.json"
    report_path = OUT / f"{kind}_report.json"

    if native_path.exists() or report_path.exists():
        raise RuntimeError(
            f"Existing output detected: {kind}. "
            "Refusing to overwrite."
        )

    system = env["DualBrainSystem"](
        env["video"]["path"],
        str(native_path),
    )

    fps = system.simulator.fps
    system.simulator.current_frame_idx = round(
        START_SECOND * fps
    )

    original_get = system.simulator.get_next_frame

    def observed_frame(freq):
        if len(control["frames"]) >= MAX_FAST_FRAMES:
            return None, None

        frame, timestamp = original_get(freq)

        if frame is not None:
            control["timestamp"] = float(timestamp)

            control["frames"].append({
                "timestamp": float(timestamp),
                "original_hash": sha(frame),
            })

        return frame, timestamp

    system.simulator.get_next_frame = observed_frame

    start = time.perf_counter()

    try:
        asyncio.run(system.run())
    finally:
        system.simulator.cap.release()

    elapsed = time.perf_counter() - start

    native = json.loads(native_path.read_text())

    stop = native.get("stop_info")
    stop = stop if isinstance(stop, dict) else {}

    trigger = stop.get("danger_timestamp")

    score, status = env["official_score"](
        trigger,
        env["gt"],
    )

    fast_requests = system.fast.requests
    slow_requests = system.slow.requests

    slow_verdicts = [
        x.get("extracted_verdict")
        for x in native.get("logs", [])
        if x.get("type") == "slow_brain"
    ]

    result = {
        "experiment": "HD-Guard E5-D",
        "condition": kind,
        "model": env["MODEL"],
        "e5b_source_sha256": source_sha,
        "official_source_sha256": hashlib.sha256(
            env["SOURCE"].read_bytes()
        ).hexdigest(),
        "native_scheduler_modified": False,
        "original_models_used": False,
        "GT_supplied_to_model": False,
        "physical_execution": False,
        "fast_mask": fast_mask,
        "slow_mask": slow_mask,
        "slow_mask_scope": (
            "all-context" if slow_mask else "none"
        ),
        "video": env["video"],
        "start_second": START_SECOND,
        "mask_from": MASK_FROM,
        "max_fast_frames": MAX_FAST_FRAMES,
        "stop_reason": stop.get("stop_reason"),
        "trigger_video_time": trigger,
        "official_status": status,
        "official_score": score,
        "wall_seconds": round(elapsed, 3),
        "fast_categories": [
            x["category"] for x in fast_requests
        ],
        "slow_verdicts": slow_verdicts,
        "slow_invoked": bool(slow_requests),
        "fast_fallbacks": sum(
            bool(x["parser_fallback"])
            for x in fast_requests
        ),
        "fast_api_errors": sum(
            x["api_error"] is not None
            for x in fast_requests
        ),
        "slow_api_errors": sum(
            bool(x["api_error"])
            for x in slow_requests
        ),
        "frame_records": control["frames"],
        "fast_input_records": control["fast"],
        "slow_input_records": control["slow"],
        "fast_requests": fast_requests,
        "slow_requests": slow_requests,
        "native_output": str(native_path),
    }

    report_path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )

    print(f"\n=== E5-D {kind} ===")
    print("Fast:", result["fast_categories"])
    print("Slow:", slow_verdicts)
    print("Slow invoked:", bool(slow_requests))
    print("Stop:", result["stop_reason"])
    print("Official:", status, score)
    print("Fast fallbacks:", result["fast_fallbacks"])
    print("API errors:",
          result["fast_api_errors"],
          result["slow_api_errors"])
    print("Wall seconds:", round(elapsed, 3))
    print("Saved:", report_path)


def forced_slow(env, source_sha):
    import cv2

    timestamps = [3.4, 3.6, 3.8, 4.0]
    cap = cv2.VideoCapture(env["video"]["path"])

    frames = []

    try:
        for t in timestamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, bgr = cap.read()

            if not ok:
                raise RuntimeError(
                    f"Video decode failed at {t}s"
                )

            frame = Image.fromarray(
                cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            )
            frames.append(frame)
    finally:
        cap.release()

    output = OUT / "forced_slow_report.json"

    if output.exists():
        raise RuntimeError("Refusing to overwrite " + str(output))

    report = {
        "experiment": "E5-D Forced-Slow",
        "scope": "Component-only, not native scheduling",
        "timestamps": timestamps,
        "model": env["MODEL"],
        "source_sha256": source_sha,
        "GT_supplied_to_model": False,
        "results": {},
    }

    for name, supplied in [
        ("clean", frames),
        ("masked", [black(f) for f in frames]),
    ]:
        slow = env["DeepSeekSlowBrain"]()
        raw, cost = slow.deep_reason(supplied)

        report["results"][name] = {
            "raw_response": raw,
            "cost_seconds": cost,
            "frame_hashes": [sha(f) for f in supplied],
            "requests": slow.requests,
        }

        print(f"\nForced Slow {name}")
        print("Response:", raw)
        print("Cost:", cost)

        output.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )

    print("Saved:", output)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--case",
        required=True,
        choices=[
            "clean",
            "fast_only",
            "slow_only",
            "shared",
            "forced_slow",
        ],
    )

    args = parser.parse_args()

    if not E5B.is_file():
        parser.error("Missing E5-B script")

    if not (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    ):
        parser.error("DeepSeek API key not configured")

    OUT.mkdir(parents=True, exist_ok=True)

    env, source_sha = load_original()

    if args.case == "forced_slow":
        forced_slow(env, source_sha)
    else:
        run_native(args.case, env, source_sha)


if __name__ == "__main__":
    main()
