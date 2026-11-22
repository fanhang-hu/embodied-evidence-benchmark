"""E6-4: read-only producer/consumer boundary inventory.

Static evidence collection only. Does not establish T1 exploitation.
No Unity, network, LLM or changes to E4/E5 sources.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / (
    "results/E6/14_t1_feasibility/"
    "e6_boundary_audit_20261025_01"
)

TARGETS = {
    "e4_validation/simulator.py": (
        "objects", "step", "prepare", "start_controller"
    ),
    "e5_validation/task_recovery_v2.py": (
        "protected_query", "lookup"
    ),
    "e5_validation/protocol.py": (
        "paired_view", "guarded"
    ),
    "e6_validation/recovery_pilot.py": (
        "paired_public", "run_episode"
    ),
}

PATTERN = re.compile(
    r"last_event\.metadata|"
    r"\.metadata\[[\"']objects|"
    r"parentReceptacles|"
    r"isToggled|"
    r"LowLevelPlanner|"
    r"Controller\(|"
    r"\.step\(|"
    r"world_state|"
    r"scene_graph|"
    r"observation",
    re.IGNORECASE,
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_target(relative, names):
    path = ROOT / relative
    require(path.is_file(), f"Missing source: {relative}")

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    found = []

    for node in tree.body:
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue

        if node.name not in names:
            continue

        found.append({
            "name": node.name,
            "line_start": node.lineno,
            "line_end": node.end_lineno,
            "arguments": [
                arg.arg for arg in node.args.args
            ],
            "source": "\n".join(
                lines[node.lineno - 1:node.end_lineno]
            ),
        })

    missing = set(names) - {
        entry["name"] for entry in found
    }

    return {
        "file": relative,
        "sha256": sha(path),
        "functions": found,
        "missing": sorted(missing),
    }


def inspect_external():
    root = ROOT / "external/SafeAgentBench"

    if not root.is_dir():
        return {
            "exists": False,
            "files_scanned": 0,
            "matches": [],
        }

    matches = []
    count = 0

    for path in sorted(root.rglob("*.py")):
        if any(
            part in {
                ".git", "__pycache__", "venv", ".venv"
            }
            for part in path.parts
        ):
            continue

        if path.stat().st_size > 1_000_000:
            continue

        count += 1

        lines = path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()

        for line_number, line in enumerate(lines, 1):
            if not PATTERN.search(line):
                continue

            if len(matches) < 500:
                matches.append({
                    "file": str(path.relative_to(ROOT)),
                    "line": line_number,
                    "text": line.strip()[:260],
                })

    return {
        "exists": True,
        "files_scanned": count,
        "match_count_retained": len(matches),
        "retention_limit": 500,
        "matches": matches,
    }


def main():
    require(
        not OUT.exists(),
        "STOP: existing E6 output must not be overwritten",
    )

    ingress_path = (
        ROOT / "results/E4/00_ingress/source_audit.json"
    )
    require(
        ingress_path.is_file(),
        "Historical E4 ingress audit missing",
    )

    ingress = json.loads(
        ingress_path.read_text(encoding="utf-8")
    )

    require(
        ingress["classification"]
        == "T0 CONTROLLED-COPY ONLY",
        "Historical attacker classification changed",
    )

    local = {
        path: inspect_target(path, names)
        for path, names in TARGETS.items()
    }

    external = inspect_external()

    report = {
        "status": "SOURCE_INVENTORY_COMPLETE",
        "T1_demonstrated": False,
        "T2_demonstrated": False,
        "historical_classification":
            ingress["classification"],
        "historical_e4_sha256": sha(ingress_path),
        "local_interfaces": local,
        "safeagentbench": external,
        "new_unity_calls": 0,
        "new_llm_calls": 0,
        "interpretation": (
            "Static matches identify candidate source paths. "
            "They do not prove that a lower-privilege actor "
            "can modify a value consumed by a safety monitor."
        ),
        "remaining_proof_obligations": [
            "Identify a distinct low-trust producer",
            "Identify the actual consumer and transport",
            "Verify producer write privileges",
            "Verify monitor and evaluator remain protected",
            "Demonstrate propagation in an unmodified consumer",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=False)

    (OUT / "inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("===== E6-4 LOCAL INTERFACES =====")

    for name, entry in local.items():
        print("\n", name)
        for fn in entry["functions"]:
            print(
                f"  L{fn['line_start']}-{fn['line_end']} "
                f"{fn['name']}("
                + ", ".join(fn["arguments"])
                + ")"
            )
        if entry["missing"]:
            print("  Missing:", entry["missing"])

    print("\n===== SAFEAGENTBENCH CANDIDATES =====")
    print(
        "Framework exists:",
        external["exists"],
    )
    print(
        "Python files scanned:",
        external["files_scanned"],
    )

    counts = {}

    for hit in external["matches"]:
        counts[hit["file"]] = (
            counts.get(hit["file"], 0) + 1
        )

    for name, count in sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0])
    )[:25]:
        print(f"  {count:3d}  {name}")

    print()
    print("E6-4 SOURCE INVENTORY: COMPLETE")
    print("Native T1 proven: NO")
    print("New Unity calls: 0")
    print("New LLM calls: 0")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
