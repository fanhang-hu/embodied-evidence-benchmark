#!/usr/bin/env python3
"""Replay archived LLM plans with the existing E4 Monitor and Unity helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from e4_validation.plan_replay import main

if __name__ == "__main__":
    main()
