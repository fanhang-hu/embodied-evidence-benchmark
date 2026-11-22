import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from ai2thor.controller import Controller

Path("results").mkdir(exist_ok=True)


def process_tree_rss_mb():
    """Python 进程及其子进程的 RSS 总和，不包含独立 Xvfb。"""
    output = subprocess.check_output(
        ["ps", "-e", "-o", "pid=,ppid=,rss="],
        text=True
    )
    processes = {}
    for line in output.splitlines():
        pid, ppid, rss = map(int, line.split()[:3])
        processes[pid] = (ppid, rss)

    pids = {os.getpid()}
    while True:
        children = {
            pid for pid, (ppid, _) in processes.items()
            if ppid in pids
        }
        new_pids = pids | children
        if new_pids == pids:
            break
        pids = new_pids

    rss_kb = sum(
        processes[pid][1]
        for pid in pids
        if pid in processes
    )
    return round(rss_kb / 1024, 1)


controller = None

report = {
    "total_steps": 200,
    "action_latencies_s": [],
    "failures": [],
    "invalid_depth_frames": 0,
    "invalid_rgb_frames": 0,
    "memory_samples": [],
    "resets": []
}

actions = [
    ("RotateRight", {}),
    ("RotateLeft", {}),
    ("LookUp", {"degrees": 15}),
    ("LookDown", {"degrees": 15}),
]

try:
    print("=== Start 200-Step Stability Test ===", flush=True)

    start = time.perf_counter()
    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    report["startup_s"] = round(time.perf_counter() - start, 3)
    print("Startup:", report["startup_s"], "s", flush=True)

    report["memory_samples"].append({
        "step": 0,
        "rss_mb": process_tree_rss_mb()
    })

    for i in range(200):

        # 在第100步后重置场景，测试恢复能力
        if i == 100:
            start = time.perf_counter()
            event = controller.reset(scene="FloorPlan1")
            elapsed = time.perf_counter() - start

            reset_result = {
                "after_step": 100,
                "reset_s": round(elapsed, 3),
                "success": bool(
                    event.metadata["lastActionSuccess"]
                )
            }
            report["resets"].append(reset_result)
            print("Reset:", reset_result, flush=True)

        action, kwargs = actions[i % len(actions)]

        start = time.perf_counter()
        event = controller.step(action=action, **kwargs)
        elapsed = time.perf_counter() - start

        report["action_latencies_s"].append(round(elapsed, 5))

        if not event.metadata["lastActionSuccess"]:
            report["failures"].append({
                "step": i + 1,
                "action": action,
                "error": event.metadata.get("errorMessage")
            })

        depth = event.depth_frame
        if depth is None or not np.isfinite(depth).all():
            report["invalid_depth_frames"] += 1

        if event.frame is None:
            report["invalid_rgb_frames"] += 1

        if (i + 1) % 25 == 0:
            rss = process_tree_rss_mb()
            report["memory_samples"].append({
                "step": i + 1,
                "rss_mb": rss
            })

            print(
                f"Step {i+1}/200 | "
                f"Latency {elapsed:.3f}s | "
                f"RSS {rss:.1f} MB",
                flush=True
            )

    times = np.array(report["action_latencies_s"])

    report["summary"] = {
        "mean_s": round(float(np.mean(times)), 3),
        "p50_s": round(float(np.percentile(times, 50)), 3),
        "p95_s": round(float(np.percentile(times, 95)), 3),
        "p99_s": round(float(np.percentile(times, 99)), 3),
        "max_s": round(float(np.max(times)), 3),
        "failure_count": len(report["failures"]),
        "invalid_depth_frames": report["invalid_depth_frames"],
        "invalid_rgb_frames": report["invalid_rgb_frames"]
    }

    print("\n=== Final Summary ===", flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)
    print("Memory samples:", report["memory_samples"], flush=True)
    print("Reset results:", report["resets"], flush=True)

    passed = (
        not report["failures"]
        and report["invalid_depth_frames"] == 0
        and report["invalid_rgb_frames"] == 0
        and all(r["success"] for r in report["resets"])
    )

    print(
        "\n200-STEP TEST PASSED" if passed
        else "\n200-STEP TEST NEEDS INVESTIGATION",
        flush=True
    )

except Exception as e:
    report["exception"] = repr(e)
    raise

finally:
    if controller is not None:
        controller.stop()

    with open("results/m0c_longrun.json", "w") as f:
        json.dump(report, f, indent=2)
