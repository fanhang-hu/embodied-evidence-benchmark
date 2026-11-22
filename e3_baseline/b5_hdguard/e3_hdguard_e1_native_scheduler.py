import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import deque
from pathlib import Path

import cv2
from PIL import Image

ROOT = Path("external/HomeSafe-Bench")
SOURCE = ROOT / "detector_dual_brain/dual_brain.py"
BASE = Path("results/E3/05_hdguard")
BASE.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hdguard_e1")

# ----------------------------------------------------------
# 1. Select one real official video
# ----------------------------------------------------------

video_candidates = sorted(
    p for p in (ROOT / "assets").rglob("*.mp4")
    if p.is_file()
)

assert video_candidates, "No official MP4 found"

valid_videos = []

for path in video_candidates:
    cap = cv2.VideoCapture(str(path))

    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, frame = cap.read()
    cap.release()

    if ok and fps > 0 and frames >= 2:
        valid_videos.append({
            "path": str(path),
            "fps": fps,
            "frames": frames,
            "duration": frames / fps,
        })

assert valid_videos, "No decodable official video"

# Choose shortest valid video for this CPU smoke test.
video = min(valid_videos, key=lambda x: x["duration"])

print("=== OFFICIAL VIDEO ===")
print(video)


# ----------------------------------------------------------
# 2. Deterministic CPU test stubs
# ----------------------------------------------------------

CURRENT = {}

class TestFastBrain:
    def __init__(self, device):
        self.device = device
        self.index = 0
        self.categories = list(CURRENT["fast_sequence"])

    def analyze_chunk(self, frame_pil):
        assert isinstance(frame_pil, Image.Image)

        i = self.index
        self.index += 1

        category = (
            self.categories[i]
            if i < len(self.categories)
            else self.categories[-1]
        )

        return {
            "category": category,
            "reason": "CPU deterministic test stub",
        }


class TestSlowBrain:
    def __init__(self):
        self.verdict = CURRENT["slow_verdict"]

    def deep_reason(self, frames_list):
        assert 1 <= len(frames_list) <= 4
        assert all(
            isinstance(x, Image.Image)
            for x in frames_list
        )

        # Simulated latency. Not actual model inference time.
        time.sleep(0.02)

        return (
            f"**VERDICT**: {self.verdict}",
            0.02,
        )


# ----------------------------------------------------------
# 3. Extract original classes without importing GPU models
# ----------------------------------------------------------

source_text = SOURCE.read_text()
tree = ast.parse(source_text, filename=str(SOURCE))

names = {
    "FileStreamSimulator",
    "DualBrainSystem",
}

selected = [
    node for node in tree.body
    if isinstance(node, ast.ClassDef)
    and node.name in names
]

assert {n.name for n in selected} == names

native_source = ast.Module(
    body=selected,
    type_ignores=[],
)

ns = {
    "__name__": "_hdguard_e1_native_",
    "asyncio": asyncio,
    "cv2": cv2,
    "json": json,
    "logging": logging,
    "os": os,
    "re": re,
    "time": time,
    "deque": deque,
    "Image": Image,
    "logger": logger,
    "DEVICE_FAST": "cpu_test_stub",
    "FREQ_IDLE": 1.0,
    "FREQ_ACTIVE": 5.0,
    "FastBrain": TestFastBrain,
    "SlowBrain": TestSlowBrain,
}

exec(
    compile(native_source, str(SOURCE), "exec"),
    ns,
)

DualBrainSystem = ns["DualBrainSystem"]

print("\nNative classes extracted: PASS")
print(
    "Source SHA256:",
    hashlib.sha256(SOURCE.read_bytes()).hexdigest()
)


# ----------------------------------------------------------
# 4. Test original scheduling and stopping logic
# ----------------------------------------------------------

SCENARIOS = {
    "red_direct_stop": {
        "fast_sequence": ["red"],
        "slow_verdict": "SAFE",
        "expected_stop": "fast_brain_red",
        "expected_slow_calls": False,
    },

    "all_green": {
        "fast_sequence": ["green"],
        "slow_verdict": "DANGER",
        "expected_stop": None,
        "expected_slow_calls": False,
    },

    "yellow_slow_danger": {
        "fast_sequence": ["yellow", "green"],
        "slow_verdict": "DANGER",
        "expected_stop": "slow_brain_confirmed",
        "expected_slow_calls": True,
    },

    "yellow_slow_safe": {
        "fast_sequence": ["yellow", "green"],
        "slow_verdict": "SAFE",
        "expected_stop": None,
        "expected_slow_calls": True,
    },
}

results = []

for name, cfg in SCENARIOS.items():
    print(f"\n=== E1 {name} ===", flush=True)

    CURRENT.clear()
    CURRENT.update(cfg)

    output_path = BASE / f"e1_{name}_native_log.json"

    system = DualBrainSystem(
        video["path"],
        str(output_path),
    )

    asyncio.run(system.run())

    assert output_path.is_file()

    saved = json.loads(output_path.read_text())
    logs = saved.get("logs", [])

    stop = saved.get("stop_info")
    stop_reason = (
        stop.get("stop_reason")
        if isinstance(stop, dict)
        else None
    )

    fast_logs = [
        x for x in logs
        if x.get("type") == "fast_brain"
    ]

    slow_logs = [
        x for x in logs
        if x.get("type") == "slow_brain"
    ]

    passed = (
        stop_reason == cfg["expected_stop"]
        and len(fast_logs) >= 1
        and (
            len(slow_logs) > 0
        ) == cfg["expected_slow_calls"]
    )

    result = {
        "name": name,
        "expected_stop": cfg["expected_stop"],
        "actual_stop": stop_reason,
        "fast_logs": len(fast_logs),
        "slow_logs": len(slow_logs),
        "fast_categories": [
            x.get("category") for x in fast_logs
        ],
        "slow_verdicts": [
            x.get("extracted_verdict") for x in slow_logs
        ],
        "pass": bool(passed),
        "original_log_file": str(output_path),
    }

    results.append(result)

    print("Stop:", stop_reason)
    print("Fast logs:", len(fast_logs))
    print("Slow logs:", len(slow_logs))
    print("PASS:", passed)


summary = {
    "tests": len(results),
    "passed": sum(r["pass"] for r in results),
    "all_pass": all(r["pass"] for r in results),
}

report = {
    "test": "HD-Guard E1",
    "scope": "official scheduler with CPU test stubs",
    "official_source": str(SOURCE),
    "official_video": video,
    "native_classes": sorted(names),
    "native_scheduler_logic_modified": False,
    "fast_model_original": False,
    "slow_model_original": False,
    "visual_model_inference": False,
    "stub_latency_is_real_model_latency": False,
    "summary": summary,
    "results": results,
}

out = BASE / "e1_native_scheduler.json"

out.write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    )
)

print("\n=== E1 SUMMARY ===")
print(summary)
print("Saved:", out)

if not summary["all_pass"]:
    raise SystemExit(1)
