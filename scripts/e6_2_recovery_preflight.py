"""E6-2: recovery interface and execution-trace preflight.

Read-only inspection of previous experiment source.
All outputs are created exclusively under results/E6.
No Unity, LLM, or prior-results modification.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OUT = (
    ROOT
    / "results/E6/02_recovery_design/"
      "e6_recovery_preflight_20261025_01"
)

E6_SCOPE = (
    ROOT
    / "results/E6/00_scope/"
      "e6_scope_20261025_01/scope_manifest.json"
)

E6_METRICS = (
    ROOT
    / "results/E6/01_metrics/"
      "e6_metrics_20261025_01/metrics.json"
)

OLD_RUNS = (
    "results/E5/task_recovery/native_20261023_01",
    "results/E5/task_recovery/native_20261023_02",
)

SOURCE_FILES = (
    "e5_validation/task_recovery_v2.py",
    "e4_validation/llm_shadow.py",
    "e4_validation/simulator.py",
    "e4_validation/protocol.py",
)

KEYWORDS = (
    "plan", "replan", "recover",
    "guard", "query", "monitor",
    "execute", "step", "cache",
)


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def load(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


def checksum(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1048576), b""
        ):
            h.update(block)

    return h.hexdigest()


def summarize_value(value):
    if isinstance(value, (bool, int, float)):
        return value

    if value is None:
        return None

    if isinstance(value, str):
        return value[:220]

    if isinstance(value, list):
        return {
            "type": "list",
            "length": len(value),
        }

    if isinstance(value, dict):
        return {
            "type": "dict",
            "keys": sorted(value.keys()),
        }

    return {"type": type(value).__name__}


def inspect_functions(path):
    if not path.is_file():
        return {
            "exists": False,
            "functions": [],
        }

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions = []

    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if any(
                word in node.name.lower()
                for word in KEYWORDS
            ):
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "args": [
                        a.arg for a in node.args.args
                    ],
                })

        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ) and any(
                    word in child.name.lower()
                    for word in KEYWORDS
                ):
                    functions.append({
                        "name": (
                            f"{node.name}.{child.name}"
                        ),
                        "line": child.lineno,
                        "args": [
                            a.arg for a in child.args.args
                        ],
                    })

    return {
        "exists": True,
        "sha256": checksum(path),
        "functions": functions,
    }


def inspect_episode(folder):
    episode_path = folder / "episode.json"
    episode = load(episode_path)

    step_paths = sorted(folder.glob("step_*.json"))
    steps = []

    for path in step_paths:
        data = load(path)

        fields = (
            "plan_index",
            "cursor",
            "candidate",
            "raw_authorization",
            "final_authorization",
            "final_reason",
            "submitted",
            "action_success",
            "unsafe_candidate",
            "violation_executed",
            "guard_query",
            "source_plan_path",
            "initial_budget_defer_control",
        )

        steps.append({
            "file": str(path.relative_to(ROOT)),
            "fields": {
                key: summarize_value(data[key])
                for key in fields
                if key in data
            },
        })

    return {
        "directory": str(folder.relative_to(ROOT)),
        "episode_fields": sorted(episode.keys()),
        "episode_metrics": {
            key: summarize_value(value)
            for key, value in episode.items()
            if any(
                token in key.lower()
                for token in (
                    "success", "violation",
                    "recover", "replan",
                    "query", "budget",
                    "safe", "status",
                )
            )
        },
        "steps": steps,
    }


def main():
    require(
        not OUT.exists(),
        "STOP: E6 preflight output already exists",
    )

    scope = load(E6_SCOPE)
    metrics = load(E6_METRICS)

    require(
        scope["status"] == "SCOPE_AUDIT_PASS"
        and metrics["status"] == "PASS",
        "E6-0/E6-1 verification missing",
    )

    original_hashes = {}
    recovery_runs = {}
    samples = []

    for relative in OLD_RUNS:
        folder = ROOT / relative
        path = folder / "records.jsonl"

        require(
            path.is_file(),
            "Missing recovery records: " + relative,
        )

        original_hashes[
            str(path.relative_to(ROOT))
        ] = checksum(path)

        rows = read_jsonl(path)

        require(
            len(rows) > 0,
            "Empty recovery record file: " + relative,
        )

        keys = sorted({
            key for row in rows
            if isinstance(row, dict)
            for key in row
        })

        recovery_runs[relative] = {
            "records": len(rows),
            "record_fields": keys,
            "case_ids": sorted({
                row["case_id"]
                for row in rows
                if isinstance(row, dict)
                and "case_id" in row
            }),
            "arms": sorted({
                str(row[key])
                for row in rows
                if isinstance(row, dict)
                for key in ("arm", "guard_arm")
                if key in row
            }),
        }

        if relative.endswith("_02"):
            episode_root = folder / "episodes"

            episode_dirs = sorted(
                p.parent
                for p in episode_root.glob(
                    "*/*/*/episode.json"
                )
            )

            require(
                len(episode_dirs) > 0,
                "No native episode directories found",
            )

            families = Counter(
                (
                    p.relative_to(episode_root).parts[0]
                    .split("_")[0]
                )
                for p in episode_dirs
            )

            recovery_runs[relative][
                "episode_directories"
            ] = len(episode_dirs)

            recovery_runs[relative][
                "family_counts"
            ] = dict(families)

            # Keep one example per (family, condition, arm).
            seen = set()

            for folder_path in episode_dirs:
                parts = folder_path.relative_to(
                    episode_root
                ).parts

                if len(parts) != 3:
                    continue

                case, condition, arm = parts

                key = (
                    case.split("_")[0],
                    condition,
                    arm,
                )

                if key in seen:
                    continue

                seen.add(key)

                samples.append(
                    inspect_episode(folder_path)
                )

    source_interfaces = {}

    for relative in SOURCE_FILES:
        path = ROOT / relative
        source_interfaces[relative] = (
            inspect_functions(path)
        )

        if path.is_file():
            original_hashes[relative] = checksum(path)

    # Confirm that inspection did not alter original files.
    for relative, old_hash in original_hashes.items():
        require(
            checksum(ROOT / relative) == old_hash,
            "Historical source changed: " + relative,
        )

    result = {
        "status": "PREFLIGHT_PASS",
        "new_unity_calls": 0,
        "new_llm_calls": 0,
        "prior_source_files_modified": False,
        "original_sha256": original_hashes,
        "recovery_runs": recovery_runs,
        "source_interfaces": source_interfaces,
        "representative_episodes": samples,
        "E6_new_experiment_status": "NOT_YET_EXECUTED",
        "planner_recovery_interface_verified": False,
        "next_required_check": (
            "Verify whether protected evidence can "
            "reach a real planner replanning interface "
            "after safety denial"
        ),
    }

    OUT.mkdir(parents=True, exist_ok=False)

    (OUT / "preflight.json").write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("===== E6-2 RECOVERY INTERFACE PREFLIGHT =====")

    for path, data in recovery_runs.items():
        print(
            f"\n{path}\n"
            f"records={data['records']}\n"
            f"cases={len(data['case_ids'])}\n"
            f"arms={data['arms']}"
        )

        if "episode_directories" in data:
            print(
                "native_episode_dirs="
                + str(data["episode_directories"])
            )

    print("\n===== Planner / Guard Functions =====")

    for path, details in source_interfaces.items():
        print("\n", path)

        if not details["exists"]:
            print("  NOT FOUND")
            continue

        for fn in details["functions"][:35]:
            print(
                f"  L{fn['line']} "
                f"{fn['name']}"
                f"({', '.join(fn['args'])})"
            )

    print("\n===== Representative Existing Traces =====")

    for example in samples[:12]:
        print("\n", example["directory"])
        print(
            "episode_metrics:",
            json.dumps(
                example["episode_metrics"],
                ensure_ascii=False,
            )[:900],
        )

        for step in example["steps"][:3]:
            print(
                "  ", Path(step["file"]).name,
                json.dumps(
                    step["fields"],
                    ensure_ascii=False,
                )[:900],
            )

    print("\nE6-2 RECOVERY PREFLIGHT: PASS")
    print("E6 new native episodes: 0")
    print("Previous E4/E5 files: READ-ONLY")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
