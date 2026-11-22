#!/usr/bin/env bash
set -euo pipefail
experiment_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$experiment_dir/../../scripts/run_experiment.py" b7_percepttwin "$@"
