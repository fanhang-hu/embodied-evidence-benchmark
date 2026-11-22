"""Grouped E4 entrypoints. Imports only the explicitly selected workflow.

Frozen scientific modules and original paths stay byte-identical. This dispatcher
does not introduce a new Planner, Monitor, Executor, or experiment protocol.
"""
from __future__ import annotations

import importlib
import json
import sys

# name: (phase, module, purpose)
COMMANDS = {
    "summarize": ("offline", "e4_validation.reporting.summary", "Audit evidence and write a NEW normalized summary"),
    "verify-pilot": ("offline", "e4_validation.verify", "Verify deterministic paired pilot and retained retries"),
    "verify-plan-replay": ("offline", "e4_validation.verify_plan_replay", "Verify C0-C4 archived-plan replay"),
    "verify-consistency": ("offline", "e4_validation.verify_consistency", "Verify original consistency replay"),
    "review-shadow": ("offline", "e4_validation.review_shadow", "Review archived pilot LLM responses"),
    "shadow-gate": ("offline", "e4_validation.shadow_gate", "Assess pilot Unity admission criteria"),
    "heldout-grade": ("offline", "e4_validation.heldout_grade", "Regrade frozen archived plans; NEW output required"),
    "shadow": ("model", "e4_validation.llm_shadow", "Pilot LLM shadow; API only with --live"),
    "heldout-llm": ("model", "e4_validation.heldout_live", "Frozen heldout LLM; API only with --live"),
    "plan-replay": ("unity", "e4_validation.plan_replay", "Pilot C0-C4 native Unity replay; zero LLM calls"),
    "heldout-replay": ("unity", "e4_validation.heldout_pairs_replay", "Frozen heldout native Unity replay; --dry-run for preflight"),
    "heldout-defense": ("unity", "e4_validation.heldout_defense_compare", "Existing paired defenses; --dry-run for preflight"),
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"list", "--help", "-h"}:
        print("Usage: python -B scripts/run_e4.py COMMAND [original module arguments]")
        for name, (phase, module, purpose) in COMMANDS.items():
            print(f"{name:22} {phase:8} {module}: {purpose}")
        print("preflight              offline  Validate all 32 frozen LLM jobs; no output/API/Unity")
        return
    command, args = argv[0], argv[1:]
    if command == "preflight":
        if args:
            raise SystemExit("preflight accepts no arguments")
        from e4_validation.heldout_pairs_replay import preflight
        frozen = preflight()
        print(json.dumps({"status": "PASS", "frozen_jobs": len(frozen),
                          "online_model_calls": 0, "Unity_calls": 0}))
        return
    if command not in COMMANDS:
        raise SystemExit(f"Unknown E4 command: {command}; use 'list'")
    module = importlib.import_module(COMMANDS[command][1])
    previous = sys.argv
    try:
        sys.argv = [module.__file__] + args
        module.main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    main()
