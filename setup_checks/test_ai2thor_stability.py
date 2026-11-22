import _bootstrap  # Workspace paths and historical cross-script imports.
from ai2thor.controller import Controller
import numpy as np
import time

c = None

try:
    t0 = time.perf_counter()

    c = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True
    )

    print(f"Startup: {time.perf_counter()-t0:.3f}s")

    initial_frame = c.last_event.frame.copy()
    initial_rotation = c.last_event.metadata["agent"]["rotation"]

    # Test 1: continuous actions
    print("\n=== Continuous Actions ===")

    for i in range(8):
        start = time.perf_counter()
        e = c.step(action="RotateRight")
        elapsed = time.perf_counter() - start

        print(
            f"Step {i+1}: "
            f"success={e.metadata['lastActionSuccess']}, "
            f"time={elapsed:.3f}s"
        )

        assert e.metadata["lastActionSuccess"]
        assert e.frame is not None
        assert e.depth_frame is not None
        assert e.frame.shape == (300, 300, 3)
        assert e.depth_frame.shape == (300, 300)

        if i == 0:
            changed = not np.array_equal(initial_frame, e.frame)
            print(f"RGB changed after rotation: {changed}")
            assert changed

    # Test 2: reset
    print("\n=== Reset Test ===")

    for i in range(3):
        start = time.perf_counter()
        e = c.reset(scene="FloorPlan1")
        elapsed = time.perf_counter() - start

        rotation = e.metadata["agent"]["rotation"]

        print(
            f"Reset {i+1}: "
            f"time={elapsed:.3f}s, "
            f"rotation={rotation}"
        )

        assert e.frame is not None
        assert e.depth_frame is not None
        assert rotation == initial_rotation

    # Test 3: depth statistics
    print("\n=== Depth Test ===")

    depth = c.last_event.depth_frame

    print("Depth shape:", depth.shape)
    print("Depth min:", np.nanmin(depth))
    print("Depth max:", np.nanmax(depth))
    print("Finite ratio:", np.isfinite(depth).mean())

    assert np.isfinite(depth).any()

    print("\nALL TESTS PASSED")

finally:
    if c is not None:
        c.stop()
