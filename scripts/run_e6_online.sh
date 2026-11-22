#!/usr/bin/env bash
set -euo pipefail
E6_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$E6_PROJECT_ROOT"
export PYTHONDONTWRITEBYTECODE=1
exec /home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m e6_validation.online_workflow "$@"
