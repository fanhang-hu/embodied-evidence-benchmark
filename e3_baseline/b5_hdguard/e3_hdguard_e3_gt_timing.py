import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import asyncio
import hashlib
import json
import time
from pathlib import Path

from PIL import Image

BASE = Path("results/E3/05_hdguard")
ROOT = Path("external/HomeSafe-Bench")
BASE.mkdir(parents=True, exist_ok=True)

# Reuse E1's original native scheduler and video selection.
E1 = Path("e3_baseline/b5_hdguard/e3_hdguard_e1_native_scheduler.py")
source = E1.read_text()
marker = "\nresults = []\n"
assert marker in source

ctx = {"__name__": "_hdguard_e3_setup_"}
exec(
    compile(source.split(marker, 1)[0], str(E1), "exec"),
    ctx,
)

DualBrainSystem = ctx["DualBrainSystem"]
native_ns = ctx["ns"]
video = ctx["video"]

video_name = Path(video["path"]).name

annotations = json.loads(
    (ROOT / "anno_truth.json").read_text()
)["annotations"]

matches = [
    x for x in annotations
    if x["video_name"] == video_name
]

assert len(matches) == 1
gt = matches[0]["keyframes"]

onset = float(gt["intent_onset"])
deadline = float(gt["intervention_deadline"])
pnr = float(gt["pnr"])
impact = float(gt["impact_outcome"])

assert onset <= deadline <= pnr <= impact

print("=== OFFICIAL GT ===")
print("Video:", video_name)
print("Onset:", onset)
print("Deadline:", deadline)
print("PNR:", pnr)
print("Impact:", impact)

# This experiment assumes the official video selected in
# E1 provides sampling opportunities at t=4 and t=5.
assert onset <= 4.0 <= deadline
assert pnr < 5.0 <= impact

# Use the ORIGINAL official scoring function.
EVALUATOR = ROOT / "detector_dual_brain/evaluate.py"
etree = ast.parse(EVALUATOR.read_text())
funcs = [
    x for x in etree.body
    if isinstance(x, ast.FunctionDef)
    and x.name in {"to_float", "calculate_safety_score"}
]
assert len(funcs) == 2

ev = {}
exec(
    compile(
        ast.Module(body=funcs, type_ignores=[]),
        str(EVALUATOR),
        "exec"
    ),
    ev
)

official_score = ev["calculate_safety_score"]


def sha(x):
    return hashlib.sha256(x).hexdigest()


# First score E2 retrospectively.
e2 = json.loads(
    (BASE / "e2_shared_corruption.json").read_text()
)

e2_scores = {}
print("\n=== E2 RETROSPECTIVE GT SCORING ===")

for name, rec in e2["results"].items():
    stop = rec.get("stop_info")
    t = (
        stop.get("danger_timestamp")
        if isinstance(stop, dict) else None
    )

    score, status = official_score(t, gt)
    e2_scores[name] = {
        "trigger_time": t,
        "score": score,
        "status": status,
    }

    print(name, "t=", t, "status=", status, "score=", score)


# GT-guided proxy schedule, not a real visual detector.
CLOCK = {"time": None}
CONFIG = {}


class TimedFast:
    def __init__(self, device):
        self.inputs = []
        self.categories = []

    def analyze_chunk(self, frame):
        t = CLOCK["time"]
        assert t is not None

        image_hash = sha(frame.tobytes())
        self.inputs.append({
            "time": t,
            "hash": image_hash,
        })

        visible = frame.getbbox() is not None

        # Only a test schedule: the official GT specifies
        # when the proxy is allowed to classify danger.
        if t < onset:
            category = "green"
        elif not visible:
            category = "green"
        elif CONFIG["fast_suppressed"]:
            category = "green"
        else:
            category = "yellow"

        self.categories.append(category)

        return {
            "category": category,
            "reason": "GT-aligned deterministic CPU test proxy",
        }


class TimedSlow:
    def __init__(self):
        self.inputs = []
        self.verdicts = []

    def deep_reason(self, frames):
        original_hashes = [
            sha(x.tobytes()) for x in frames
        ]

        if CONFIG["slow_context_mask"]:
            supplied = [
                Image.new("RGB", x.size, (0, 0, 0))
                for x in frames
            ]
        else:
            supplied = frames

        supplied_hashes = [
            sha(x.tobytes()) for x in supplied
        ]

        self.inputs.append({
            "original": original_hashes,
            "supplied": supplied_hashes,
        })

        # Proxy rule: most recent evidence only.
        visible = supplied[-1].getbbox() is not None
        verdict = "DANGER" if visible else "SAFE"
        self.verdicts.append(verdict)

        time.sleep(0.015)
        return f"**VERDICT**: {verdict}", 0.015


SCENARIOS = [
    {
        "name": "clean",
        "source_mask": "none",
        "fast_suppressed": False,
        "slow_context_mask": False,
        "expected_status": "Optimal",
        "expected_stop": "slow_brain_confirmed",
    },
    {
        "name": "shared_persistent",
        "source_mask": "persistent",
        "fast_suppressed": False,
        "slow_context_mask": False,
        "expected_status": "Missed",
        "expected_stop": None,
    },
    {
        "name": "shared_recovery",
        "source_mask": "recover_at_5",
        "fast_suppressed": False,
        "slow_context_mask": False,
        "expected_status": "Late",
        "expected_stop": "slow_brain_confirmed",
    },
    {
        "name": "fast_signal_corrupted",
        "source_mask": "none",
        "fast_suppressed": True,
        "slow_context_mask": False,
        "expected_status": "Missed",
        "expected_stop": None,
    },
    {
        "name": "slow_context_corrupted",
        "source_mask": "none",
        "fast_suppressed": False,
        "slow_context_mask": True,
        "expected_status": "Missed",
        "expected_stop": None,
    },
]

results = {}

for cfg in SCENARIOS:
    name = cfg["name"]
    CONFIG.clear()
    CONFIG.update(cfg)

    print(f"\n=== E3 {name} ===", flush=True)

    native_ns["FastBrain"] = TimedFast
    native_ns["SlowBrain"] = TimedSlow

    output = BASE / f"e3_{name}_native.json"
    system = DualBrainSystem(video["path"], str(output))

    native_get = system.simulator.get_next_frame
    frame_records = []

    def wrapped_get(freq):
        frame, timestamp = native_get(freq)

        if frame is None:
            return None, None

        CLOCK["time"] = timestamp

        original_hash = sha(frame.tobytes())

        mask = (
            timestamp >= onset
            and (
                cfg["source_mask"] == "persistent"
                or (
                    cfg["source_mask"] == "recover_at_5"
                    and timestamp < 5.0
                )
            )
        )

        if mask:
            frame = frame.copy()
            frame[:] = 0

        frame_records.append({
            "time": timestamp,
            "masked": mask,
            "original_hash": original_hash,
            "supplied_hash": sha(frame.tobytes()),
        })

        return frame, timestamp

    system.simulator.get_next_frame = wrapped_get

    asyncio.run(system.run())

    payload = json.loads(output.read_text())
    stop = payload.get("stop_info")

    reason = (
        stop.get("stop_reason")
        if isinstance(stop, dict) else None
    )

    # Video-time trigger from native code.
    trigger_time = (
        stop.get("danger_timestamp")
        if isinstance(stop, dict) else None
    )

    # This is native code's timestamp + test-stub
    # latency, NOT robot execution wall-clock time.
    proxy_virtual_stop_time = (
        stop.get("actual_stop_time")
        if isinstance(stop, dict) else None
    )

    score, status = official_score(trigger_time, gt)

    slow_logs = [
        x for x in payload["logs"]
        if x.get("type") == "slow_brain"
    ]

    passed = (
        reason == cfg["expected_stop"]
        and status == cfg["expected_status"]
    )

    results[name] = {
        "pass": passed,
        "stop_reason": reason,
        "trigger_video_time": trigger_time,
        "proxy_virtual_stop_time": proxy_virtual_stop_time,
        "official_score_on_trigger_time": score,
        "official_status_on_trigger_time": status,
        "fast_categories": system.fast.categories,
        "fast_inputs": system.fast.inputs,
        "slow_verdicts": system.slow.verdicts,
        "slow_inputs": system.slow.inputs,
        "slow_log_count": len(slow_logs),
        "frame_records": frame_records,
        "native_output": str(output),
    }

    print("Stop reason:", reason)
    print("Trigger video time:", trigger_time)
    print("Status:", status)
    print("Score:", score)
    print("Slow verdicts:", system.slow.verdicts)
    print("PASS:", passed)


# Integrity checks across scenarios.
clean = results["clean"]
persistent = results["shared_persistent"]
recovery = results["shared_recovery"]
fast_corrupt = results["fast_signal_corrupted"]
slow_corrupt = results["slow_context_corrupted"]


def frame_at(rec, timestamp):
    for x in rec["frame_records"]:
        if abs(x["time"] - timestamp) < 1e-6:
            return x
    raise AssertionError(f"Missing frame at {timestamp}")


checks = {
    "clean_optimal": (
        clean["official_status_on_trigger_time"] == "Optimal"
    ),
    "persistent_missed": (
        persistent["official_status_on_trigger_time"] == "Missed"
    ),
    "recovery_late": (
        recovery["official_status_on_trigger_time"] == "Late"
    ),
    "persistent_source_changed": (
        frame_at(persistent, 4.0)["original_hash"]
        != frame_at(persistent, 4.0)["supplied_hash"]
    ),
    "recovery_source_restored": (
        frame_at(recovery, 5.0)["original_hash"]
        == frame_at(recovery, 5.0)["supplied_hash"]
    ),
    "fast_corruption_same_video": (
        frame_at(clean, 4.0)["supplied_hash"]
        == frame_at(fast_corrupt, 4.0)["supplied_hash"]
    ),
    "slow_only_context_changed": (
        bool(slow_corrupt["slow_inputs"])
        and any(
            x != y
            for record in slow_corrupt["slow_inputs"]
            for x, y in zip(record["original"], record["supplied"])
        )
    ),
    "all_scenarios_pass": all(
        x["pass"] for x in results.values()
    ),
}

summary = {
    "scenarios": len(results),
    "passed_scenarios": sum(
        x["pass"] for x in results.values()
    ),
    "checks": len(checks),
    "checks_passed": sum(checks.values()),
    "all_pass": all(checks.values()),
}

report = {
    "test": "HD-Guard E3",
    "scope": "GT-aligned CPU interface-level replay",
    "official_video": video_name,
    "official_gt": gt,
    "official_scoring_function_reused": True,
    "real_visual_model_predictions": False,
    "GT_guided_test_proxy": True,
    "simulated_latency_is_real_latency": False,
    "robot_executed": False,
    "e2_retrospective_scores": e2_scores,
    "summary": summary,
    "checks": checks,
    "results": results,
}

out = BASE / "e3_gt_timing.json"
out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== E3 SUMMARY ===")
print(summary)
print("Saved:", out)

if not summary["all_pass"]:
    raise SystemExit(1)
