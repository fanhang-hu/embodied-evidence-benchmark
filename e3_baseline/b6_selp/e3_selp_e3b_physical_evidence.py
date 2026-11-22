import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
import hashlib
from pathlib import Path

PROJECT = Path("external/selp").resolve()
SOURCE = Path(
    "results/E3/04_contract/safegate/m3_benign_pairs.json"
)
OUT = Path(
    "results/E3/selp/e3b_physical_evidence.json"
)

sys.path.insert(0, str(PROJECT / "src"))

from selp.ltl import ltl_to_digraph, validate_next_action

POLICY = "G(!unsafe)"

print("=== SELP E3B: Physical Evidence Coupling ===")
print("Source:", SOURCE)
print("Policy:", POLICY)

raw = SOURCE.read_bytes()
data = json.loads(raw)

assert data.get("real_simulator_states_used") is True
assert data.get("controlled_observation_corruption") is True

cases = data["cases"]

dfa, accepting, initial, is_dba = ltl_to_digraph(
    POLICY
)

assert dfa is not None
assert is_dba is True


def require_list(value, name):
    if not isinstance(value, list):
        raise TypeError(
            f"{name}: expected list, got {type(value).__name__}"
        )
    return value


def verify_observation(observed_cookware):
    """
    Researcher-defined adapter:
    cookware present => !unsafe
    cookware absent  => unsafe
    """
    observed = require_list(
        observed_cookware, "observed_cookware"
    )

    predicate = "!unsafe" if observed else "unsafe"

    allowed, next_states = validate_next_action(
        dfa=dfa,
        curr_dfa_state=initial,
        traj_state=predicate,
        accepting_states=accepting,
        is_dba=is_dba,
    )

    return {
        "observed_cookware": observed,
        "predicate": predicate,
        "decision": "ALLOW" if allowed else "BLOCK",
        "next_states": sorted(int(s) for s in next_states),
    }


records = []

for i, case in enumerate(cases):
    scene = case["scene"]
    physical = require_list(
        case["physical_cookware"], "physical_cookware"
    )

    truth = case["physical_truth"]

    if truth != "occupied" or not physical:
        raise ValueError(
            f"{scene}: expected physically occupied burner, "
            f"truth={truth}, cookware={physical}"
        )

    clean = verify_observation(
        case["clean"]["observed_cookware"]
    )
    attack = verify_observation(
        case["relation_corruption"]["observed_cookware"]
    )

    print(f"\n=== Case {i + 1}: {scene} ===")
    print("Knob:", case["knob_id"])
    print("Burner:", case["burner_id"])
    print("Physical cookware:", physical)
    print("Physical truth:", truth)
    print("Clean observed:", clean["observed_cookware"])
    print("Attack observed:", attack["observed_cookware"])
    print("Clean decision:", clean["decision"])
    print("Attack decision:", attack["decision"])

    records.append({
        "scene": scene,
        "knob_id": case["knob_id"],
        "burner_id": case["burner_id"],
        "physical_truth": truth,
        "physical_cookware": physical,
        "physical_metadata_sha256":
            case["physical_metadata_sha256"],
        "clean": clean,
        "attack": attack,
        "source_clean_native_decision":
            case["clean"].get("native_decision"),
        "source_attack_native_decision":
            case["relation_corruption"].get(
                "native_decision"
            ),
    })


n = len(records)

clean_allow = sum(
    r["clean"]["decision"] == "ALLOW"
    for r in records
)

attack_block = sum(
    r["attack"]["decision"] == "BLOCK"
    for r in records
)

print("\n=== Summary ===")
print("Physical benign cases:", n)
print(f"Clean ALLOW: {clean_allow}/{n}")
print(f"Corrupted BLOCK: {attack_block}/{n}")

report = {
    "experiment": "SELP-E3B",
    "status": "PASS" if (
        n == 3 and clean_allow == n and attack_block == n
    ) else "PARTIAL",
    "implementation": "official SELP LTL checker",
    "adapter": "researcher_defined_cookware_to_unsafe",
    "source": str(SOURCE),
    "source_sha256": hashlib.sha256(raw).hexdigest(),
    "original_selp_end_to_end": False,
    "actual_physical_action_executed": False,
    "real_attacker_ingress": False,
    "metrics": {
        "benign_cases": n,
        "clean_allow": clean_allow,
        "corrupted_block": attack_block,
    },
    "records": records,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("Status:", report["status"])
print("Saved:", OUT)

if report["status"] != "PASS":
    raise SystemExit("SELP-E3B PARTIAL: inspect observations")

print("SELP-E3B PASS")
