#!/usr/bin/env bash
set -euo pipefail

ENV_DIR="$HOME/.venvs/embguard-cpu"

echo "=== EMBGuard E3B: CPU PyTorch Setup ==="

echo
echo "=== Create isolated environment ==="

mkdir -p "$HOME/.venvs"

if [ ! -e "$ENV_DIR" ]; then
    python -m venv "$ENV_DIR"
fi

if [ ! -x "$ENV_DIR/bin/python" ]; then
    echo "ERROR: Invalid virtual environment"
    exit 1
fi

echo "Environment: $ENV_DIR"

echo
echo "=== Python / pip ==="

"$ENV_DIR/bin/python" --version
"$ENV_DIR/bin/python" -m pip --version

echo
echo "=== Install CPU-only PyTorch ==="

"$ENV_DIR/bin/python" -m pip install \
    --no-cache-dir \
    --disable-pip-version-check \
    --timeout 30 \
    --retries 2 \
    "torch==2.5.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

echo
echo "=== CPU runtime validation ==="

"$ENV_DIR/bin/python" - <<'PY'
import torch
import time

print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("CPU threads:", torch.get_num_threads())

torch.set_num_threads(6)

a = torch.randn(512, 512)
b = torch.randn(512, 512)

start = time.perf_counter()
c = a @ b
elapsed = time.perf_counter() - start

print("Matrix shape:", tuple(c.shape))
print("Matrix result finite:", bool(torch.isfinite(c).all()))
print("Matrix test seconds:", round(elapsed, 4))

assert not torch.cuda.is_available()
assert torch.isfinite(c).all()

print("CPU PYTORCH TEST PASS")
PY

echo
echo "EMBGUARD-E3B COMPLETED"
