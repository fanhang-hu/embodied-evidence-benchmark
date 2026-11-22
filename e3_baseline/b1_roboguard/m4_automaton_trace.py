import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path

import spot

sys.path.insert(
    0,
    str(Path("external/RoboGuard/src").resolve())
)
from roboguard.synthesis import ControlSynthesis

ROOT = Path("results/baseline_audit")
saved = json.loads(
    (ROOT / "m4_relabel_route_check.json").read_text()
)

report = {}

for case in ("clean", "attack"):
    record = json.loads(
        (ROOT / f"m4_relabel_{case}_eval.json").read_text()
    )

    assert record["status"] == "SUCCESS"

    checker = ControlSynthesis(
        record["normalized_constraints"]
    )

    plan = [
        tuple(x)
        for x in saved[case]["CONNECTED_ROUTE"]["plan"]
    ]

    actions = checker.format_plan_for_checking(plan)
    formatted = [
        checker.clean_formula(x) for x in actions
    ]

    ap_set = set(checker.automaton.ap())
    state = checker.automaton.get_init_state_number()

    print(f"\n=== {case.upper()} ===")
    print("Atomic propositions:")
    print(sorted(map(str, ap_set)))

    rows = []

    for original, action in zip(actions, formatted):
        if action.startswith("goto"):
            checker.current_pos = spot.formula(action)

        valuation = checker.action_to_formula(
            spot.formula(action)
        )

        source_state = state
        matched = []

        for edge in checker.automaton.out(source_state):
            condition = spot.formula(
                spot.bdd_format_formula(
                    checker.bdict, edge.cond
                )
            )

            if spot.contains(condition, valuation):
                matched.append({
                    "destination": int(edge.dst),
                    "condition": str(condition),
                })

                # 与原版源码完全一致：
                # 最后一个匹配的边决定状态。
                state = edge.dst

        accepting = bool(
            checker.automaton.state_is_accepting(state)
        )

        row = {
            "action": original,
            "action_in_automaton_ap": (
                spot.formula(action) in ap_set
            ),
            "source_state": int(source_state),
            "destination_state": int(state),
            "matched_edges": matched,
            "matched_count": len(matched),
            "state_accepting": accepting,
        }

        rows.append(row)

        print(f"\nAction: {original}")
        print("In automaton AP:", row["action_in_automaton_ap"])
        print("Source state:", source_state)
        print("Matched edges:", len(matched))
        print("Destinations:", [
            x["destination"] for x in matched
        ])
        print("Final state:", state)
        print("State accepting:", accepting)

    expected = saved[case]["CONNECTED_ROUTE"]

    observed_steps = [
        [x["action"], x["state_accepting"]]
        for x in rows
    ]

    trace_matches_saved = (
        observed_steps == expected["steps"]
        and rows[-1]["state_accepting"] == expected["accepted"]
    )

    print("\nMatches previous validator output:",
          trace_matches_saved)

    report[case] = {
        "rows": rows,
        "trace_matches_saved": trace_matches_saved,
        "previous_verdict": expected["accepted"],
    }

    if not trace_matches_saved:
        raise RuntimeError(
            f"{case}: trace differs from original validator"
        )

path = ROOT / "m4_automaton_trace.json"
path.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\nSaved:", path)
print("M4-7F TRACE COMPLETED")
