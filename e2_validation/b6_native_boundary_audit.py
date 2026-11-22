"""E2-B6: Native input boundary and attacker-access audit.

Static evidence collection only. Does not prove exploitability.
No modifications to original repositories.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.

import hashlib
import json
import os
import re
import stat
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "results/e2b6_native_boundary_audit.json"

sources = {
    "native_snapshot":
        "external/safe-hierarchical-embodied-ai/"
        "src/ae_rl/execution/kitchen_safety.py",

    "native_controller":
        "external/safe-hierarchical-embodied-ai/"
        "src/ae_rl/rl/interaction/controller.py",

    "native_safety":
        "external/safe-hierarchical-embodied-ai/"
        "src/ae_rl/execution/safety.py",

    "safeagentbench_vision":
        "external/SafeAgentBench/methods/map_vlm.py",

    "safeagentbench_utils":
        "external/SafeAgentBench/utils.py",

    "adapted_state_provider":
        "e1_validation/kitchen_state_provider_pipeline.py",
}

patterns = {
    "native_snapshot": (
        r"def build_kitchen_snapshot|"
        r"def check_toggle_scene_safety|"
        r"last_event|metadata|"
        r"parentReceptacles|"
        r"knob_to_burner"
    ),
    "native_controller": (
        r"def toggle_object|"
        r"build_kitchen_snapshot|"
        r"check_toggle_scene_safety|"
        r"_rl_execute|"
        r"ToggleObjectOn|"
        r"last_event"
    ),
    "native_safety": (
        r"def check_action_safety|"
        r"temperature|material|metadata"
    ),
    "safeagentbench_vision": (
        r"last_event.frame|"
        r"all_objs|"
        r"encoded_image|"
        r"multi_agent_vision_planning|"
        r"execute_low_level_plan"
    ),
    "safeagentbench_utils": (
        r"def all_objs|"
        r"def execute_low_level_plan|"
        r"last_event.metadata|"
        r"llm_skill_interact"
    ),
    "adapted_state_provider": (
        r"subprocess|"
        r"m6_state_feed|"
        r"read_text|"
        r"write_text|"
        r"corrupted.json"
    ),
}

report = {
    "experiment": "E2-B6",
    "classification": "static native ingress audit",
    "uid": os.getuid(),
    "gid": os.getgid(),
    "sources": {},
    "permissions": {},
    "repo_reference_scan": {},
    "conclusions_not_yet_proven": [
        "Independent low-privilege attacker can modify native state",
        "Original native monitor consumes VLM output",
        "Original native monitor consumes experiment JSON files",
        "Original system accepts stale camera evidence",
        "End-to-end unauthorized action execution",
    ],
}

print("=== E2-B6 Native Boundary Audit ===")
print("Current UID:", os.getuid(), "GID:", os.getgid())

for name, relative in sources.items():
    path = ROOT / relative

    if not path.is_file():
        report["sources"][name] = {
            "file": relative,
            "present": False,
        }
        print(f"\n{name}: FILE NOT FOUND: {relative}")
        continue

    content = path.read_bytes()
    lines = content.decode(
        "utf-8", errors="replace"
    ).splitlines()

    regex = re.compile(patterns[name], re.I)

    hits = [
        {"line": i, "text": line.strip()[:220]}
        for i, line in enumerate(lines, 1)
        if regex.search(line)
    ]

    report["sources"][name] = {
        "file": relative,
        "present": True,
        "sha256": hashlib.sha256(content).hexdigest(),
        "total_matching_lines": len(hits),
        "matching_lines": hits,
    }

    print(f"\n=== {name} ===")
    print("File:", relative)
    print("SHA256:", hashlib.sha256(content).hexdigest())
    print("Matches:", len(hits))

    for hit in hits[:25]:
        print(f"  L{hit['line']}: {hit['text']}")

# Search only the original native repository.
# A negative result is not a proof that every dynamic path is absent.
native_root = (
    ROOT / "external/safe-hierarchical-embodied-ai/src/ae_rl"
)

references = {
    "experiment_feed_names":
        re.compile(
            r"m6_state_feed|corrupted\.json|"
            r"stove_view\.png|e2b5"
        ),
    "image_or_visual_inputs":
        re.compile(
            r"last_event\.frame|"
            r"vision_payload|"
            r"image_url|"
            r"encoded_image"
        ),
}

if native_root.is_dir():
    for category, regex in references.items():
        matches = []

        for path in sorted(native_root.rglob("*.py")):
            text = path.read_text(
                encoding="utf-8", errors="replace"
            )

            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append({
                        "file": str(path.relative_to(ROOT)),
                        "line": i,
                        "text": line.strip()[:200],
                    })

        report["repo_reference_scan"][category] = matches

        print(f"\n=== Native repo: {category} ===")
        print("Matching lines:", len(matches))

        for match in matches[:25]:
            print(
                f"{match['file']}:{match['line']}: "
                f"{match['text']}"
            )

paths = [
    ROOT / "results/m6_state_feed",
    ROOT / "results/m6_state_feed/corrupted.json",
    ROOT / "results/e2b5",
    ROOT / "results/e2b5/t0_pan_on_target_roi.png",
]

print("\n=== File Permissions ===")

for path in paths:
    if not path.exists():
        continue

    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)

    record = {
        "path": str(path.relative_to(ROOT)),
        "mode": oct(mode),
        "owner_uid": st.st_uid,
        "owner_gid": st.st_gid,
        "current_process_can_write": os.access(
            path, os.W_OK
        ),
    }

    report["permissions"][record["path"]] = record
    print(record)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))

print("\nSaved:", OUT)
print("E2-B6 STATIC AUDIT COMPLETE")
print("EXPLOITABILITY NOT ESTABLISHED")
