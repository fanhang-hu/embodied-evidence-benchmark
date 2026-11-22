"""Read-only paired audit of E4 Heldout original and two defenses."""
import json
from pathlib import Path

BASE = Path("results/E4/07_heldout")
RUNS = {
    "original": "heldout_unity_01",
    "consistency": "heldout_consistency_02",
    "fresh": "heldout_fresh_02",
}

def load(name):
    p = BASE / RUNS[name] / "records.jsonl"
    rows = [
        json.loads(line)
        for line in p.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 32, (name, len(rows))
    assert all(r["status"] == "COMPLETED" for r in rows)

    def key(r):
        return (
            r["case_id"],
            r["safe_initial"],
            r["condition"],
        )

    result = {key(r): r for r in rows}
    assert len(result) == 32

    for r in rows:
        for field in (
            "unsafe_authorized",
            "violation_executed",
            "task_success",
        ):
            assert isinstance(r[field], bool), (
                name, key(r), field, r.get(field)
            )

    return result

data = {name: load(name) for name in RUNS}
keys = set(data["original"])

for name in ("consistency", "fresh"):
    assert set(data[name]) == keys

    for key in sorted(keys):
        a = data["original"][key]
        b = data[name][key]

        assert (
            a["proposed_plan"]["actions"]
            == b["proposed_plan"]["actions"]
        ), (name, key, "PLAN_CHANGED")

        assert b["paired_baseline_matched"] is True
        assert b["task_critical_state_matched"] is True

print("PAIRED INTEGRITY: PASS (32/32 per defense)")

for name, records in data.items():
    rows = list(records.values())

    print("\n==========", name.upper(), "==========")
    print("Completed:", len(rows))
    print("UAR:", sum(r["unsafe_authorized"] for r in rows))
    print("Violations:", sum(
        r["violation_executed"] for r in rows
    ))
    print("Task success:", sum(
        r["task_success"] for r in rows
    ), "/ 32")

    for family in ("attribute", "relation"):
        for condition in ("clean", "shared"):
            subset = [
                r for r in rows
                if r["family"] == family
                and r["condition"] == condition
                and r["safe_initial"] is False
            ]
            print(
                family, condition,
                "N:", len(subset),
                "UAR:", sum(r["unsafe_authorized"] for r in subset),
                "Exec:", sum(
                    r["violation_executed"] for r in subset
                ),
                "Task:", sum(r["task_success"] for r in subset),
            )

    for condition in ("clean", "shared"):
        benign = [
            r for r in rows
            if r["safe_initial"] is True
            and r["condition"] == condition
        ]
        print(
            "Safe initial /", condition,
            "task success:",
            sum(r["task_success"] for r in benign),
            "/", len(benign)
        )

for name in ("consistency", "fresh"):
    before = data["original"]
    after = data[name]

    prevented = sum(
        before[k]["violation_executed"]
        and not after[k]["violation_executed"]
        for k in keys
    )
    lost = sum(
        before[k]["task_success"]
        and not after[k]["task_success"]
        for k in keys
    )
    gained = sum(
        not before[k]["task_success"]
        and after[k]["task_success"]
        for k in keys
    )

    print("\nPAIRED CHANGE:", name)
    print("Violations prevented:", prevented)
    print("Previously successful tasks lost:", lost)
    print("Previously failed tasks recovered:", gained)

print("\nAUDIT COMPLETE")
