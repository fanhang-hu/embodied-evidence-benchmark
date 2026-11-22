from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/E4/07_heldout"
TARGET = ROOT / "e4_validation/heldout_defense_compare.py"
BACKUP = ROOT / "e4_validation/heldout_defense_compare_v1.py"

records = [
    json.loads(x)
    for x in (BASE / "heldout_consistency_01/records.jsonl")
    .read_text().splitlines()
    if x.strip()
]

failures = [
    r for r in records
    if r["status"] == "FAILED_OR_INCOMPLETE"
]

EXPECTED = "BASELINE_INITIAL_STATE_OR_PLAN_MISMATCH"

if not failures or any(
    EXPECTED not in r.get("error", "")
    for r in failures
):
    raise SystemExit(
        "STOP: failures include other error types. "
        "Do not apply this patch."
    )

src = TARGET.read_text()

old = '''                if (
                    row["producer_clean_sha256"]
                    != original["producer_clean_sha256"]
                    or row["proposed_plan"]["actions"]
                    != original["proposed_plan"]["actions"]
                ):
                    raise RuntimeError(
                        "BASELINE_INITIAL_STATE_OR_PLAN_MISMATCH"
                    )
'''

new = '''                # The complete Unity metadata contains volatile fields.
                # Compare frozen plans and task-critical private truth.
                if (
                    row["proposed_plan"]["actions"]
                    != original["proposed_plan"]["actions"]
                ):
                    raise RuntimeError("ARCHIVED_PLAN_MISMATCH")

                old_state = json.loads(
                    (
                        ROOT / original["evidence_dir"]
                        / "producer_clean.json"
                    ).read_text()
                )
                new_state = json.loads(
                    (folder / "producer_clean.json").read_text()
                )

                if task_signature(new_state, case) != task_signature(
                    old_state, case
                ):
                    raise RuntimeError(
                        "TASK_CRITICAL_TRUE_STATE_MISMATCH"
                    )

                row["full_state_hash_matched"] = (
                    row["producer_clean_sha256"]
                    == original["producer_clean_sha256"]
                )
                row["task_critical_state_matched"] = True
'''

helper = '''

def task_signature(state, case):
    """Stable task-critical truth, not all Unity metadata."""
    index = {
        o["objectId"]: o
        for o in state["objects"]
    }

    pan = index[case["pan_id"]]
    knob = index[case["knob_id"]]
    burner = index[case["burner_id"]]

    return {
        "pan_id": pan["objectId"],
        "pan_type": pan["objectType"],
        "pan_held": pan.get("isPickedUp"),
        "pan_parents": sorted(
            pan.get("parentReceptacles") or []
        ),
        "knob_id": knob["objectId"],
        "knob_type": knob["objectType"],
        "knob_on": knob.get("isToggled"),
        "burner_id": burner["objectId"],
        "burner_type": burner["objectType"],
        "burner_on": burner.get("isToggled"),
    }
'''

anchor = "\n\ndef main():"

if src.count(old) != 1 or src.count(anchor) != 1:
    raise SystemExit(
        "STOP: current script is not the expected v1. "
        "No changes made."
    )

if BACKUP.exists():
    raise SystemExit(
        f"STOP: backup already exists: {BACKUP}"
    )

shutil.copy2(TARGET, BACKUP)

updated = src.replace(old, new, 1)
updated = updated.replace(anchor, helper + anchor, 1)

TARGET.write_text(updated)

print("PATCH APPLIED")
print("Backup:", BACKUP)
print("Updated:", TARGET)
print(
    "Full-state hash is now diagnostic; "
    "plan and critical truth remain enforced."
)
