import _bootstrap  # Workspace paths and historical cross-script imports.
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path("results/E3/05_optional/robosafe")
SRC = ROOT / "r2_trace_v1/manifest.json"
OUT = ROOT / "r5a_backward_predicates.json"

assert SRC.is_file()
assert not OUT.exists(), f"Refusing overwrite: {OUT}"

manifest = json.loads(SRC.read_text())
results = []


def read_jsonl(path):
    return [
        json.loads(x)
        for x in path.read_text().splitlines()
        if x.strip()
    ]


def verify_original_evidence(trace):
    for row in trace:
        for path_key, hash_key in (
            ("rgb_path", "rgb_sha256"),
            ("state_path", "state_sha256"),
        ):
            path = Path(row[path_key])
            assert path.is_file(), path
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == row[hash_key], path


def check_temporal_predicates(trace):
    """
    Mechanism-level temporal checker.

    Prerequisite:
        Initial observation must precede executed actions.

    Obligation:
        In this specific inspection protocol, RotateRight
        must be followed immediately by successful RotateLeft.

    Adjacency:
        Each executed command must match its own simulator
        receipt, with ordered timestamps.
    """
    problems = {
        "prerequisite": [],
        "obligation": [],
        "adjacency": [],
    }

    observed = bool(
        trace
        and trace[0].get("label") == "INITIAL_OBSERVATION"
        and trace[0].get("submitted_action") is None
    )

    if not observed:
        problems["prerequisite"].append(
            "missing_initial_observation"
        )

    previous_time = None

    for i, event in enumerate(trace):
        now = event.get("capture_monotonic_ns")

        if (
            not isinstance(now, int)
            or (
                previous_time is not None
                and now <= previous_time
            )
        ):
            problems["adjacency"].append(
                f"invalid_time_order_at_{i}"
            )

        previous_time = now

        action = event.get("submitted_action")

        if action is None:
            continue

        if not observed:
            problems["prerequisite"].append(
                f"action_without_observation_at_{i}"
            )

        if event.get("last_action") != action:
            problems["adjacency"].append(
                f"receipt_action_mismatch_at_{i}"
            )

        if event.get("last_action_success") is not True:
            problems["adjacency"].append(
                f"execution_not_confirmed_at_{i}"
            )

        if action == "RotateRight":
            if i + 1 >= len(trace):
                problems["obligation"].append(
                    f"missing_restore_after_{i}"
                )
            else:
                next_event = trace[i + 1]
                if (
                    next_event.get("submitted_action")
                    != "RotateLeft"
                    or next_event.get("last_action_success")
                    is not True
                ):
                    problems["obligation"].append(
                        f"restore_not_fulfilled_after_{i}"
                    )

    return {
        "prerequisite": (
            "PASS" if not problems["prerequisite"]
            else "VIOLATION"
        ),
        "obligation": (
            "PASS" if not problems["obligation"]
            else "VIOLATION"
        ),
        "adjacency": (
            "PASS" if not problems["adjacency"]
            else "VIOLATION"
        ),
        "violations": problems,
    }


for spec in manifest["scenes"]:
    scene = spec["scene"]
    trace = read_jsonl(Path(spec["trace_file"]))

    assert len(trace) == 3
    verify_original_evidence(trace)

    real = check_temporal_predicates(trace)

    assert all(
        real[name] == "PASS"
        for name in (
            "prerequisite",
            "obligation",
            "adjacency",
        )
    ), (scene, real)

    tests = {}

    # Controlled negative #1: remove the initial observation.
    missing_observation = copy.deepcopy(trace[1:])
    tests["missing_observation"] = (
        check_temporal_predicates(missing_observation)
    )

    # Controlled negative #2: remove restoration action.
    missing_restore = copy.deepcopy(trace[:2])
    tests["missing_restore"] = (
        check_temporal_predicates(missing_restore)
    )

    # Controlled negative #3: falsify command receipt.
    wrong_receipt = copy.deepcopy(trace)
    wrong_receipt[1]["last_action"] = "RotateLeft"
    tests["wrong_receipt"] = (
        check_temporal_predicates(wrong_receipt)
    )

    assert (
        tests["missing_observation"]["prerequisite"]
        == "VIOLATION"
    )
    assert (
        tests["missing_restore"]["obligation"]
        == "VIOLATION"
    )
    assert (
        tests["wrong_receipt"]["adjacency"]
        == "VIOLATION"
    )

    results.append({
        "scene": scene,
        "original_execution_trace": real,
        "controlled_mutations": tests,
        "original_trace_unchanged": True,
    })

    print(f"\n=== {scene} ===")
    print("Real trace:", {
        k: real[k] for k in (
            "prerequisite", "obligation", "adjacency"
        )
    })

    for name, result in tests.items():
        failed = [
            k for k in (
                "prerequisite", "obligation", "adjacency"
            )
            if result[k] == "VIOLATION"
        ]
        print(name, "detected:", failed)


report = {
    "experiment": "RoboSafe-R5A",
    "implementation": "researcher_authored_temporal_checker",
    "official_robosafe_reproduced": False,
    "temporal_predicates": [
        "prerequisite",
        "obligation",
        "adjacency",
    ],
    "obligation_scope": "R2_inspection_protocol_only",
    "real_executed_traces": len(results),
    "controlled_mutated_traces": 3 * len(results),
    "model_generated_predicates": False,
    "stove_safety_violation_tested": False,
    "unsafe_physical_actions_executed": False,
    "results": results,
}

OUT.write_text(json.dumps(
    report, indent=2, ensure_ascii=False
))

print("\n=== ROBOSAFE-R5A SUMMARY ===")
print("Real traces:", len(results))
print("Controlled negative traces:", 3 * len(results))
print("All temporal assertions: PASS")
print("Official RoboSafe reproduced: NO")
print("Saved:", OUT)
print("ROBOSAFE-R5A COMPLETED")
