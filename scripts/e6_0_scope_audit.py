"""E6-0: read-only scope, provenance and metric eligibility audit.

Uses existing E4/E5 evidence. Never invokes Unity or LLM APIs.
Does not reclassify a T0 experiment as T1/T2.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BASE_E4 = Path("results/E4")
BASE_E5 = Path("results/E5/C_temporal_validity")
BASE_E6 = Path("results/E6")

OUT = BASE_E6 / "00_scope/e6_scope_20261025_01"

INPUTS = {
    "e4_ingress": (
        BASE_E4 / "00_ingress/source_audit.json"
    ),
    "e4_acceptance": (
        BASE_E4 / "04_validation/acceptance.json"
    ),
    "e5_final": (
        BASE_E5
        / "28_final/e5_c_final_20261025_01/summary.json"
    ),
}

EXPECTED_STAGES = {
    "C1": 15,
    "C2": 9,
    "C3": 30,
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def read_json(path):
    full = ROOT / path
    require(full.is_file(), f"Missing file: {path}")
    return json.loads(full.read_text(encoding="utf-8"))


def sha256(path):
    h = hashlib.sha256()

    with (ROOT / path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


def main():
    require(
        not (ROOT / OUT).exists(),
        "STOP: E6-0 output already exists",
    )

    # E4 threat boundary.
    ingress = read_json(INPUTS["e4_ingress"])
    e4 = read_json(INPUTS["e4_acceptance"])

    require(
        ingress["classification"]
        == "T0 CONTROLLED-COPY ONLY",
        "E4 ingress classification changed",
    )

    require(
        ingress["native_T1_demonstrated"] is False
        and ingress["native_T2_demonstrated"] is False,
        "E4 threat-level assumptions changed",
    )

    require(
        e4["status"] == "PASS_T0_MECHANISM_PILOT"
        and e4["paired_conditions"] == 84
        and e4["LLM_planner_tested"] is False,
        "E4 acceptance does not match frozen experiment",
    )

    # E5-C cross-stage audit.
    e5 = read_json(INPUTS["e5_final"])

    require(
        e5["status"] == "PASS"
        and e5["formal_native_episodes"] == 54
        and e5["distinct_case_configurations"] == 8
        and e5["pilot_excluded"] is True,
        "E5-C final cross-stage audit is invalid",
    )

    require(
        set(e5["stages"])
        == set(EXPECTED_STAGES),
        "Unexpected E5-C stage set",
    )

    evidence_hashes = {
        name: sha256(path)
        for name, path in INPUTS.items()
    }

    stage_scope = {}
    case_sets = {}

    for name, expected in EXPECTED_STAGES.items():
        info = e5["stages"][name]
        run = Path(info["run"])
        records_path = run / "records.jsonl"

        require(
            info["episodes"] == expected,
            f"{name}: episode count mismatch",
        )

        require(
            sha256(records_path)
            == info["records_sha256"],
            f"{name}: records hash mismatch",
        )

        records = [
            json.loads(line)
            for line in (
                ROOT / records_path
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        require(
            len(records) == expected
            and all(
                record["status"] == "COMPLETED"
                for record in records
            ),
            f"{name}: missing/incomplete native episodes",
        )

        actual_cases = {
            record["case_id"] for record in records
        }

        require(
            actual_cases == set(info["case_ids"]),
            f"{name}: case identity mismatch",
        )

        case_sets[name] = actual_cases
        evidence_hashes[
            f"{name}_records"
        ] = sha256(records_path)

        stage_scope[name] = {
            "formal_episodes": expected,
            "case_ids": sorted(actual_cases),
            "native_execution": True,
            "archived_real_llm_plan": True,
            "online_llm_regeneration": False,
            "attacker_level": "T0",
            "implementation_level": "adapted_monitor",
            "source_records": str(records_path),
            "source_audit": info["audit"],
            "reported_comparison": info["comparison"],
        }

        print(
            f"{name}: episodes={expected}, "
            f"cases={len(actual_cases)}, "
            "record_hash=PASS",
            flush=True,
        )

    require(
        case_sets["C1"] == case_sets["C3"],
        "C1/C3 case reuse mismatch",
    )

    require(
        case_sets["C1"].isdisjoint(case_sets["C2"]),
        "Attribute/relation case overlap",
    )

    # This is a scope manifest, NOT a claim of E6 success.
    tracks = {
        "E4_joint_adapted": {
            "attacker_level": "T0",
            "implementation_level": "adapted_system",
            "planner": "online_deterministic_task_planner",
            "monitor": "frozen_research_policy",
            "executor": "native_AI2THOR",
            "experimental_conditions": 84,
            "scene_clusters": 3,
            "fact_families": [
                "attribute",
                "relation",
            ],
            "can_measure_joint_propagation": True,
            "native_T1_proven": False,
            "protected_fresh": (
                "simulator_authoritative_X_upper_bound"
            ),
        },
        "E5_C1_attribute_staleness": {
            **stage_scope["C1"],
            "candidate_origin": "frozen_archived_llm_plan",
            "fact_type": "attribute",
        },
        "E5_C2_relation_staleness": {
            **stage_scope["C2"],
            "candidate_origin": "frozen_archived_llm_plan",
            "fact_type": "relation",
        },
        "E5_C3_conditional_notification": {
            **stage_scope["C3"],
            "candidate_origin": "frozen_archived_llm_plan",
            "fact_type": "attribute",
            "trusted_notification": (
                "assumed_complete_single_writer"
            ),
            "silent_loss_detection_proven": False,
        },
    }

    missing_evidence = [
        "Native lower-privilege T1 producer-write access",
        "T2 deployed Planner-Monitor-Executor attack chain",
        "Online LLM planner regeneration for E5-C",
        "Independent heldout clusters for E5-C",
        "Same-permission protected-sensor deployment proof",
        "Full sensor/LLM/VLM/end-to-end latency decomposition",
        "Realistic timeout/recovery and benign utility budgets",
        "Silent loss detection for C3 notifications",
    ]

    scope = {
        "status": "SCOPE_AUDIT_PASS",
        "E6_completed": False,
        "E6_native_episodes_so_far": 0,
        "source_hashes": evidence_hashes,
        "threat_classification": "T0",
        "native_T1_proven": False,
        "native_T2_proven": False,
        "E4_paired_conditions": 84,
        "E5_C_formal_episodes": 54,
        "E5_C_unique_configurations": 8,
        "tracks": tracks,
        "missing_evidence": missing_evidence,
        "primary_e6_metrics": [
            "UAR_probe",
            "UAR_closed_loop_when_planner_runs",
            "Simulation_Execution_ASR",
            "Benign_Authorization_Rate",
            "Benign_Task_Success_Rate",
            "False_Block_Rate",
            "False_Defer_Rate",
            "Recovery_Rate",
            "Protected_Query_Cost",
            "End_to_End_Latency",
        ],
        "comparison_rule": (
            "Never pool fixed-candidate probes, "
            "deterministic planner actions, archived LLM "
            "replays, and native deployed systems"
        ),
    }

    output = ROOT / OUT
    output.mkdir(parents=True, exist_ok=False)

    (output / "scope_manifest.json").write_text(
        json.dumps(
            scope, ensure_ascii=False, indent=2
        ) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# E6-0 Evidence Scope Audit",
        "",
        "**Status:** SCOPE_AUDIT_PASS",
        "",
        "## Existing tracks",
        "",
        "| Track | Evidence | Permission | Planner |",
        "|---|---|---|---|",
        "| E4 | 84 paired conditions | T0 | Adapted deterministic |",
        "| E5-C1 | 15 native episodes | T0 | Archived DeepSeek |",
        "| E5-C2 | 9 native episodes | T0 | Archived DeepSeek |",
        "| E5-C3 | 30 native episodes | Conditional T0 | Archived DeepSeek |",
        "",
        "## Evidence still missing",
        "",
        *[f"- {item}" for item in missing_evidence],
        "",
        "## Next step",
        "",
        "Harmonize stage-specific denominators and metrics",
        "without pooling incompatible tracks.",
        "Then identify genuinely missing strong baseline",
        "and end-to-end cost measurements.",
        "",
    ]

    (output / "scope_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print("E6-0 SCOPE AUDIT: PASS")
    print("E4: 84 controlled T0 paired conditions")
    print("E5-C: 54 independently audited native episodes")
    print("Native T1/T2: NOT DEMONSTRATED")
    print("New Unity calls: 0")
    print("New LLM calls: 0")
    print("Output:", output)


if __name__ == "__main__":
    main()
