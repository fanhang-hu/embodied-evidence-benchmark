"""Create a corrected read-only audit without modifying frozen sources."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = root / "e5_validation/a_consistent_pollution/report.py"
dst = root / "e5_validation/a_consistent_pollution/report_v2.py"

if dst.exists():
    raise SystemExit(f"STOP: destination already exists: {dst}")

source = src.read_text(encoding="utf-8")

old = '''            assert field_diff(truth, observed) == s["attack_diff"]'''

new = '''            # Runner computes attack_diff at check time, BEFORE
            # the optional protected Pass and submission-time snapshot.
            # Audit the recorded diff against that exact source.
            check_truth = read_json(
                step_dir / "S_true_check_private.json"
            )
            assert field_diff(check_truth, observed) == s["attack_diff"], (
                r["case_id"], arm, i, "ATTACK_DIFF_MISMATCH"
            )

            # The later submission snapshot remains the authoritative
            # basis for unsafe-action and execution-violation evaluation.
            # Verify that task-critical facts did not change meanwhile.
            from e5_validation.task_recovery_v2 import signature
            assert signature(check_truth, case) == signature(truth, case), (
                r["case_id"], arm, i,
                "POLICY_FACT_CHANGED_BETWEEN_CHECK_AND_SUBMIT"
            )'''

if source.count(old) != 1:
    raise SystemExit(
        "STOP: expected audit statement not found exactly once."
    )

dst.write_text(source.replace(old, new, 1), encoding="utf-8")

print("CREATED:", dst)
print("Original frozen report remains unchanged:", src)
