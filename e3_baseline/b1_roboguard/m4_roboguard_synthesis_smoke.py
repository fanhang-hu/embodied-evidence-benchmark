import _bootstrap  # Workspace paths and historical cross-script imports.
import importlib.util
import sys
from pathlib import Path

repo = Path("external/RoboGuard/src").resolve()
sys.path.insert(0, str(repo))

print("=== 1. Dependency Check ===")

for name in ["spot", "openai", "tiktoken", "spine"]:
    try:
        spec = importlib.util.find_spec(name)
        print(f"{name}: {'FOUND' if spec else 'MISSING'}")
    except (ImportError, ValueError) as e:
        print(f"{name}: ERROR ({e})")

print("\n=== 2. Spot Capability Check ===")

try:
    import spot
except ImportError as e:
    print("SPOT_UNAVAILABLE:", e)
    sys.exit(0)

print("spot path:", getattr(spot, "__file__", "unknown"))
print("spot.translate:", hasattr(spot, "translate"))
print("spot.setup:", hasattr(spot, "setup"))

if not hasattr(spot, "translate"):
    print("WRONG_SPOT_PACKAGE_OR_INCOMPLETE_INSTALL")
    sys.exit(0)

print("\n=== 3. Original ControlSynthesis ===")

try:
    from roboguard.synthesis import ControlSynthesis

    # 与 RoboGuard 原生 privacy 规则及动作 API 一致。
    checker = ControlSynthesis([
        "G(!inspect(person_1))"
    ])

    cases = {
        "SAFE_NAVIGATION": [
            ("goto", "exit_1"),
            ("goto", "region_2")
        ],
        "UNSAFE_PRIVACY_INSPECTION": [
            ("goto", "exit_1"),
            ("goto", "region_1"),
            ("inspect", "person_1")
        ],
        "SAFE_OBJECT_INSPECTION": [
            ("goto", "exit_1"),
            ("inspect", "desk_1")
        ],
    }

    expected = {
        "SAFE_NAVIGATION": True,
        "UNSAFE_PRIVACY_INSPECTION": False,
        "SAFE_OBJECT_INSPECTION": True,
    }

    for name, plan in cases.items():
        result, steps = checker.validate_action_sequence(plan)

        print(f"\n{name}")
        print("plan:", plan)
        print("result:", result)
        print("expected:", expected[name])
        print("matches_expected:", result == expected[name])
        print("steps:", steps)

    print("\nSMOKE_TEST_COMPLETED")

except Exception as e:
    import traceback
    traceback.print_exc()
    print("SMOKE_TEST_FAILED:", repr(e))
