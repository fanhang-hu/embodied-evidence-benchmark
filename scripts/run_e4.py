#!/usr/bin/env python3
"""Project-root-independent entrypoint for the grouped E4 workflow."""
from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == "__main__":
    # Existing frozen modules resolve several relative CLI paths against cwd.
    os.chdir(PROJECT_ROOT)
    from e4_validation.workflow import main
    main()
