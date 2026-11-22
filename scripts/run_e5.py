#!/usr/bin/env python3
"""E5 grouped entrypoint. Native source/binding runs query Unity but execute no probes."""
from pathlib import Path
import importlib
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {"freeze": "e5_validation.freeze", "source": "e5_validation.source",
            "binding": "e5_validation.binding", "verify": "e5_validation.verify"}


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    if len(sys.argv) < 2 or sys.argv[1] in {"list", "--help", "-h"}:
        print("Usage: python -B scripts/run_e5.py COMMAND [arguments]")
        for name, module in COMMANDS.items():
            print(name, module)
        return
    command = sys.argv.pop(1)
    if command not in COMMANDS:
        raise SystemExit("Unknown E5 command: " + command)
    importlib.import_module(COMMANDS[command]).main()


if __name__ == "__main__":
    main()
