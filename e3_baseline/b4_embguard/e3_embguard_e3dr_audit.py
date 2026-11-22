#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = _bootstrap.ROOT
OUT = ROOT / "results/E3/06_embguard/e3dr_audit.json"
REPO = "EMBGuard/EMBGuard-2B"

def version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None

def file_record(p):
    try:
        return {
            "path": str(p),
            "size_bytes": p.stat().st_size,
            "size_gib": round(p.stat().st_size / 2**30, 3)
        }
    except OSError:
        return None

def files_under(root, pattern, max_results=30):
    if not root.exists():
        return []
    result = []
    try:
        for p in root.rglob(pattern):
            if p.is_file():
                entry = file_record(p)
                if entry:
                    result.append(entry)
                if len(result) >= max_results:
                    break
    except (OSError, PermissionError):
        pass
    return result

hf_home = Path(
    os.environ.get(
        "HF_HOME",
        str(Path.home() / ".cache/huggingface")
    )
).expanduser()

hub_cache = Path(
    os.environ.get(
        "HF_HUB_CACHE",
        str(hf_home / "hub")
    )
).expanduser()

emb_cache = (
    hub_cache / "models--EMBGuard--EMBGuard-2B"
)

roots = [
    ROOT / "external",
    ROOT / "models",
    ROOT / "checkpoints",
    ROOT / "results/E3/06_embguard",
]

disk = shutil.disk_usage(ROOT)

result = {
    "python": sys.executable,
    "versions": {
        "torch": version("torch"),
        "transformers": version("transformers"),
        "huggingface_hub": version("huggingface_hub"),
        "hf_xet": version("hf_xet"),
        "safetensors": version("safetensors"),
    },
    "disk": {
        "free_gib": round(disk.free / 2**30, 2),
        "total_gib": round(disk.total / 2**30, 2),
    },
    "hf_home": str(hf_home),
    "hub_cache": str(hub_cache),
    "model_cache_exists": emb_cache.exists(),
    "cached_model_files": (
        files_under(emb_cache, "*.safetensors")
        + files_under(emb_cache, "*.incomplete")
        + files_under(emb_cache, "*.lock")
    ),
    "candidate_model_files": [
        item
        for root in roots
        for item in files_under(root, "model.safetensors")
    ],
    "candidate_metadata": [
        item
        for root in roots
        for item in files_under(root, "config.json", 10)
        if "embguard" in item["path"].lower()
    ][:30],
    "model_repo": REPO,
    "network": {},
}

# Short public-URL checks only. Do not send credentials.
urls = {
    "huggingface": "https://huggingface.co",
    "model_config":
      "https://huggingface.co/EMBGuard/EMBGuard-2B/resolve/main/config.json",
}

for name, url in urls.items():
    try:
        run = subprocess.run(
            [
                "curl", "-L", "-sS",
                "-o", "/dev/null",
                "--connect-timeout", "5",
                "--max-time", "15",
                "-w", "%{http_code}"
                     " %{time_total}",
                url
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        result["network"][name] = {
            "exit_code": run.returncode,
            "http_and_seconds": run.stdout.strip(),
            "error": run.stderr.strip()[:250],
        }
    except Exception as exc:
        result["network"][name] = {
            "error": type(exc).__name__
        }

OUT.write_text(
    json.dumps(result, ensure_ascii=False, indent=2)
)

print("=== EMBGUARD E3D-R AUDIT ===")
print("Python:", result["python"])
print("Versions:", result["versions"])
print("Free disk GiB:", result["disk"]["free_gib"])
print("HF cache:", result["hub_cache"])
print("Model cache exists:", result["model_cache_exists"])

print("\nCached weight / partial files:")
for x in result["cached_model_files"]:
    print(x["size_gib"], "GiB", x["path"])

print("\nOther model weight candidates:")
for x in result["candidate_model_files"]:
    print(x["size_gib"], "GiB", x["path"])

print("\nNetwork:")
for name, x in result["network"].items():
    print(name, x)

print("\nSaved:", OUT)
