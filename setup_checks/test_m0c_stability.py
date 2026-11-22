import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import time
from pathlib import Path

import numpy as np
from ai2thor.controller import Controller

Path("results").mkdir(exist_ok=True)

controller = None
report = {"scenes": []}

try:
    print("=== Initialize Controller ===", flush=True)
    t0 = time.perf_counter()

    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    report["startup_s"] = round(time.perf_counter() - t0, 3)
    print("Startup:", report["startup_s"], "s", flush=True)

    for scene in ["FloorPlan1", "FloorPlan2"]:
        print(f"\n=== {scene} ===", flush=True)

        t0 = time.perf_counter()
        event = controller.reset(scene=scene)
        reset_s = time.perf_counter() - t0

        times = []
        failures = []
        invalid_depth_frames = 0

        for i in range(20):
            start = time.perf_counter()
            event = controller.step(action="RotateRight")
            elapsed = time.perf_counter() - start

            times.append(elapsed)

            if not event.metadata["lastActionSuccess"]:
                failures.append({
                    "step": i + 1,
                    "error": event.metadata.get("errorMessage")
                })

            depth = event.depth_frame
            if depth is None or not np.isfinite(depth).all():
                invalid_depth_frames += 1

            if (i + 1) % 5 == 0:
                print(f"Completed {i+1}/20", flush=True)

        result = {
            "scene": scene,
            "reset_s": round(reset_s, 3),
            "steps": 20,
            "mean_s": round(float(np.mean(times)), 3),
            "p50_s": round(float(np.percentile(times, 50)), 3),
            "p95_s": round(float(np.percentile(times, 95)), 3),
            "p99_s": round(float(np.percentile(times, 99)), 3),
            "max_s": round(float(np.max(times)), 3),
            "failure_count": len(failures),
            "failures": failures,
            "invalid_depth_frames": invalid_depth_frames
        }

        report["scenes"].append(result)
        print(json.dumps(result, indent=2), flush=True)

finally:
    if controller is not None:
        controller.stop()

    with open("results/m0c_perf.json", "w") as f:
        json.dump(report, f, indent=2)

print("\nM0-C INITIAL TEST FINISHED", flush=True)
