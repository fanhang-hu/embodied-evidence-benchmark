import _bootstrap  # Workspace paths and historical cross-script imports.
import asyncio
import hashlib
import json
import time
from pathlib import Path

BASE = Path("results/E3/05_hdguard")
BASE.mkdir(parents=True, exist_ok=True)

E1 = Path("e3_baseline/b5_hdguard/e3_hdguard_e1_native_scheduler.py")
source = E1.read_text()

marker = "\nresults = []\n"
assert marker in source, "E1 script structure changed"

# Reuse the exact native classes and video selection
# already validated in E1, without executing E1 tests.
ctx = {"__name__": "_hdguard_e2_setup_"}
exec(
    compile(source.split(marker, 1)[0], str(E1), "exec"),
    ctx,
)

DualBrainSystem = ctx["DualBrainSystem"]
native_ns = ctx["ns"]
video = ctx["video"]

CONFIG = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class CPUFast:
    """
    Researcher-controlled proxy, not MiniCPM.
    It records the image it actually received.
    """

    def __init__(self, device):
        self.mode = CONFIG["fast_mode"]
        self.signal = CONFIG.get("signal")
        self.records = []

    def analyze_chunk(self, frame):
        self.records.append(digest(frame.tobytes()))
        index = len(self.records)

        if self.mode == "signal":
            category = self.signal

        elif self.mode == "pixel":
            # Deliberately simple visual proxy:
            # nonblack -> yellow, black -> green.
            category = (
                "yellow" if frame.getbbox() else "green"
            )

        elif self.mode == "yellow_once":
            category = (
                "yellow" if index == 1 else "green"
            )

        else:
            raise ValueError(self.mode)

        return {
            "category": category,
            "reason": "E2 deterministic CPU proxy",
        }


class CPUSlow:
    """
    Researcher-controlled proxy, not Qwen3-VL.
    Verdict depends on the received frame data.
    """

    def __init__(self):
        self.inputs = []
        self.verdicts = []

    def deep_reason(self, frames):
        hashes = [
            digest(frame.tobytes())
            for frame in frames
        ]

        self.inputs.append(hashes)

        visible = any(
            frame.getbbox() is not None
            for frame in frames
        )

        verdict = "DANGER" if visible else "SAFE"
        self.verdicts.append(verdict)

        # Test-only delay; not model latency.
        time.sleep(0.015)

        return f"**VERDICT**: {verdict}", 0.015


SCENARIOS = [
    {
        "name": "S_clean_red",
        "fast_mode": "signal",
        "signal": "red",
        "mask": "none",
        "expected_stop": "fast_brain_red",
        "expected_slow": False,
    },
    {
        "name": "S_corrupted_green",
        "fast_mode": "signal",
        "signal": "green",
        "mask": "none",
        "expected_stop": None,
        "expected_slow": False,
    },
    {
        "name": "V_clean",
        "fast_mode": "pixel",
        "mask": "none",
        "expected_stop": "slow_brain_confirmed",
        "expected_slow": True,
    },
    {
        "name": "V_corrupted",
        "fast_mode": "pixel",
        "mask": "all",
        "expected_stop": None,
        "expected_slow": False,
    },
    {
        "name": "V_recovery",
        "fast_mode": "pixel",
        "mask": "first",
        "expected_stop": "slow_brain_confirmed",
        "expected_slow": True,
    },
    {
        "name": "C_clean",
        "fast_mode": "yellow_once",
        "mask": "none",
        "expected_stop": "slow_brain_confirmed",
        "expected_slow": True,
    },
    {
        "name": "C_corrupted",
        "fast_mode": "yellow_once",
        "mask": "all",
        "expected_stop": None,
        "expected_slow": True,
    },
]

results = {}

for cfg in SCENARIOS:
    name = cfg["name"]

    print(f"\n=== E2 {name} ===", flush=True)

    CONFIG.clear()
    CONFIG.update(cfg)

    native_ns["FastBrain"] = CPUFast
    native_ns["SlowBrain"] = CPUSlow

    output = BASE / f"e2_{name}_native.json"

    system = DualBrainSystem(
        video["path"],
        str(output),
    )

    # Intercept only the external video-frame source.
    # Original DualBrainSystem.run() is unchanged.
    native_get = system.simulator.get_next_frame

    frame_events = []
    frame_index = 0

    def supplied_frame(freq):
        nonlocal_dummy = None  # no change to native scheduler
        global frame_index

        frame, timestamp = native_get(freq)

        if frame is None:
            return None, None

        frame_index += 1

        original_hash = digest(frame.tobytes())

        mask = (
            cfg["mask"] == "all"
            or (
                cfg["mask"] == "first"
                and frame_index == 1
            )
        )

        if mask:
            frame = frame.copy()
            frame[:] = 0

        frame_events.append({
            "timestamp": timestamp,
            "masked": mask,
            "original_hash": original_hash,
            "supplied_hash": digest(frame.tobytes()),
        })

        return frame, timestamp

    system.simulator.get_next_frame = supplied_frame

    asyncio.run(system.run())

    payload = json.loads(output.read_text())
    stop_info = payload.get("stop_info")

    stop_reason = (
        stop_info.get("stop_reason")
        if isinstance(stop_info, dict)
        else None
    )

    fast_logs = [
        x for x in payload["logs"]
        if x.get("type") == "fast_brain"
    ]

    slow_logs = [
        x for x in payload["logs"]
        if x.get("type") == "slow_brain"
    ]

    slow_called = len(slow_logs) > 0

    passed = (
        stop_reason == cfg["expected_stop"]
        and slow_called == cfg["expected_slow"]
        and len(fast_logs) > 0
    )

    results[name] = {
        "pass": passed,
        "stop_reason": stop_reason,
        "stop_info": stop_info,
        "fast_categories": [
            x.get("category") for x in fast_logs
        ],
        "slow_verdicts": [
            x.get("extracted_verdict")
            for x in slow_logs
        ],
        "slow_trigger_times": [
            x.get("trigger_timestamp")
            for x in slow_logs
        ],
        "fast_input_hashes": system.fast.records,
        "slow_input_hashes": system.slow.inputs,
        "frame_events": frame_events,
        "native_log": str(output),
    }

    print("Stop:", stop_reason)
    print("Fast:", results[name]["fast_categories"])
    print("Slow:", results[name]["slow_verdicts"])
    print("PASS:", passed)


# ----------------------------------------------------------
# Cross-case checks
# ----------------------------------------------------------

def first_fast(name):
    return results[name]["fast_input_hashes"][0]


checks = {
    # Signal tampering: identical input frame,
    # but different supplied risk category.
    "S_same_visual_input": (
        first_fast("S_clean_red")
        == first_fast("S_corrupted_green")
    ),

    "S_output_changes_stop": (
        results["S_clean_red"]["stop_reason"]
        == "fast_brain_red"
        and results["S_corrupted_green"]["stop_reason"]
        is None
    ),

    # Shared frame evidence changes.
    "V_frame_changed": (
        first_fast("V_clean")
        != first_fast("V_corrupted")
    ),

    "V_clean_stops_corrupt_misses": (
        results["V_clean"]["stop_reason"]
        == "slow_brain_confirmed"
        and results["V_corrupted"]["stop_reason"]
        is None
    ),

    "V_recovery_stops": (
        results["V_recovery"]["stop_reason"]
        == "slow_brain_confirmed"
    ),

    # SlowBrain receives the same initial evidence
    # previously consumed by FastBrain.
    "C_clean_shared_evidence": (
        first_fast("C_clean")
        in results["C_clean"]["slow_input_hashes"][0]
    ),

    "C_corrupt_shared_evidence": (
        first_fast("C_corrupted")
        in results["C_corrupted"]["slow_input_hashes"][0]
    ),

    "C_clean_danger_corrupt_safe": (
        "DANGER" in results["C_clean"]["slow_verdicts"]
        and "SAFE" in results["C_corrupted"]["slow_verdicts"]
    ),
}

for cfg in SCENARIOS:
    checks[f"scenario_{cfg['name']}"] = (
        results[cfg["name"]]["pass"]
    )

summary = {
    "scenarios": len(SCENARIOS),
    "scenario_passed": sum(
        results[x["name"]]["pass"]
        for x in SCENARIOS
    ),
    "checks": len(checks),
    "checks_passed": sum(checks.values()),
    "all_pass": all(checks.values()),
}

report = {
    "test": "HD-Guard E2",
    "scope": "CPU interface-level evidence corruption",
    "official_scheduler_modified": False,
    "original_video_used": video["path"],
    "original_visual_models_used": False,
    "cpu_proxy_output": True,
    "physical_hazard_detection_measured": False,
    "real_execution_asr": False,
    "simulated_latency_not_model_latency": True,
    "summary": summary,
    "checks": checks,
    "results": results,
}

out = BASE / "e2_shared_corruption.json"

out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== E2 SUMMARY ===")
print(summary)
print("Saved:", out)

if not summary["all_pass"]:
    raise SystemExit(1)
