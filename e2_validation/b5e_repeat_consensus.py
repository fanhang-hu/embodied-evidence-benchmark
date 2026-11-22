"""E2-B5E: Repeatability, voting and stale-evidence replay.

Offline analysis of previously recorded VLM outputs.
No additional API calls, simulator actions, or live attacks.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import json
from pathlib import Path

R = Path("results")
OUT = R / "e2b5/e2b5e_repeat_consensus.json"

assert not OUT.exists(), f"Already exists: {OUT}"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


repeat = load(R / "e2b5/e2b5d_vlm_repeatability.json")
transition = load(R / "e2b5/real_state_transition.json")
attack = load(R / "m5_geometry_consistency.json")
replay = load(R / "e2b5/stale_visual_replay.json")

t0 = transition["t0_real_pan_on_target"]
t1 = transition["t1_real_pan_removed"]

assert t0["pan_on_target"] is True
assert t1["pan_on_target"] is False
assert t0["native_decision"] == "ALLOW"
assert t1["native_decision"] == "BLOCK"
assert attack["a2"]["native_decision"] == "ALLOW"

assert (
    repeat["image_sha256"]["new_t0"]
    == t0["roi_sha256"]
)

t0_image = Path(t0["roi_file"])
assert sha(t0_image) == t0["roi_sha256"]

predictions = [
    c["prediction"]
    for c in repeat["calls"]
    if c["image"] == "new_t0"
]

assert len(predictions) == 3
assert all(
    p in ("yes", "no", "unknown", "invalid")
    for p in predictions
)

fresh_t1 = replay["vlm"]["t1"]["prediction"]


def fuse(native, visual):
    if native == "BLOCK":
        return "BLOCK"

    if native != "ALLOW":
        return "DEFER"

    return "ALLOW" if visual == "yes" else "DEFER"


def majority(values):
    yes = values.count("yes")
    no = values.count("no")
    n = len(values)

    if yes > n / 2:
        return "yes"
    if no > n / 2:
        return "no"

    return "unknown"


def unanimous(values):
    if all(x == "yes" for x in values):
        return "yes"
    if all(x == "no" for x in values):
        return "no"
    return "unknown"


voting = {
    "individual_predictions": predictions,
    "majority": majority(predictions),
    "unanimous": unanimous(predictions),
}

# T0: actual benign scene, native ALLOW.
t0_single = [
    fuse("ALLOW", p)
    for p in predictions
]

t0_majority = fuse("ALLOW", voting["majority"])
t0_unanimous = fuse("ALLOW", voting["unanimous"])

# T1: real empty target, clean native BLOCK.
t1_clean_stale = [
    fuse("BLOCK", p)
    for p in predictions
]

# T1 + A2: explicitly COUNTERFACTUAL.
# The native A2 ALLOW is imported from an earlier synthetic test.
# The cached image originates from this session's real T0.
t1_a2_stale = [
    fuse("ALLOW", p)
    for p in predictions
]

t1_a2_majority = fuse(
    "ALLOW", voting["majority"]
)

t1_a2_unanimous = fuse(
    "ALLOW", voting["unanimous"]
)

t1_a2_fresh = fuse("ALLOW", fresh_t1)

report = {
    "experiment": "E2-B5E",
    "classification": (
        "offline repeatability and stale-evidence counterfactual"
    ),
    "real_t0_target_has_pan": True,
    "real_t1_target_has_pan": False,
    "t0_roi_sha256": t0["roi_sha256"],
    "t0_repeated_predictions": predictions,
    "voting": voting,
    "real_t0_benign": {
        "native": "ALLOW",
        "one_shot_results": t0_single,
        "majority_result": t0_majority,
        "unanimous_result": t0_unanimous,
    },
    "real_t1_clean_with_stale_t0": {
        "native": "BLOCK",
        "one_shot_results": t1_clean_stale,
    },
    "counterfactual_t1_a2_with_stale_t0": {
        "native": "ALLOW",
        "one_shot_results": t1_a2_stale,
        "majority_result": t1_a2_majority,
        "unanimous_result": t1_a2_unanimous,
        "unsafe_one_shot_authorizations": sum(
            x == "ALLOW" for x in t1_a2_stale
        ),
    },
    "counterfactual_t1_a2_with_fresh_t1": {
        "native": "ALLOW",
        "fresh_visual": fresh_t1,
        "fused": t1_a2_fresh,
    },
    "api_calls_this_run": 0,
    "simulator_actions_this_run": 0,
    "live_attack": False,
    "limitations": [
        "Only three recorded repeat calls for the T0 image",
        "Recorded calls are reused, not independent trials here",
        "A2 metadata result comes from a different prior experiment",
        "No real adversarial cache or camera replay",
        "Voting cannot authenticate evidence freshness",
        "No runtime authorization or physical execution",
    ],
}

OUT.write_text(json.dumps(report, indent=2))

print("=== E2-B5E Repeat and Freshness Audit ===")
print("T0 repeated visual predictions:", predictions)
print("Majority:", voting["majority"])
print("Unanimous:", voting["unanimous"])
print()
print("T0 legitimate, one-shot:", t0_single)
print("T0 legitimate, majority:", t0_majority)
print("T0 legitimate, unanimous:", t0_unanimous)
print()
print("T1 clean native + stale T0:", t1_clean_stale)
print("T1 A2 + stale T0, counterfactual:", t1_a2_stale)
print("T1 A2 + stale T0, majority:", t1_a2_majority)
print("T1 A2 + stale T0, unanimous:", t1_a2_unanimous)
print("T1 A2 + fresh T1:", t1_a2_fresh)

assert len(set(predictions)) > 1
assert all(x == "BLOCK" for x in t1_clean_stale)
assert t1_a2_fresh == "DEFER"

print()
print("Saved:", OUT)
print("E2-B5E OFFLINE AUDIT COMPLETE")
