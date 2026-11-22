import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("external/HomeSafe-Bench")
BASE = Path("results/E3/05_hdguard")
ARCHIVE = Path("external/homesafe_repo.zip")

BASE.mkdir(parents=True, exist_ok=True)

FILES = {
    "readme": ROOT / "README.md",
    "annotations": ROOT / "anno_truth.json",
    "dual_brain": ROOT / "detector_dual_brain/dual_brain.py",
    "evaluator": ROOT / "detector_dual_brain/evaluate.py",
    "batch_runner": ROOT / "detector_dual_brain/run_batch_test.sh",
    "slow_runner": ROOT / "detector_dual_brain/run_slow_brain.sh",
}

# ==========================================================
# E0-A: Official source integrity
# ==========================================================

print("\n=== E0-A: OFFICIAL SOURCE ===")

for name, path in FILES.items():
    exists = path.is_file()
    print(f"{name}: {'PASS' if exists else 'MISSING'}")

    if not exists:
        raise FileNotFoundError(path)

for name in ("dual_brain", "evaluator"):
    path = FILES[name]
    ast.parse(path.read_text(), filename=str(path))
    print(f"{name} AST: PASS")

zip_sha256 = None

if ARCHIVE.is_file():
    h = hashlib.sha256()
    with ARCHIVE.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    zip_sha256 = h.hexdigest()

print("Source ZIP SHA256:", zip_sha256)


# ==========================================================
# E0-B: Official annotations
# ==========================================================

print("\n=== E0-B: ANNOTATIONS ===")

data = json.loads(FILES["annotations"].read_text())
items = data["annotations"]

assert isinstance(items, list)

metadata = data.get("metadata", {})

print("Metadata:", metadata)
print("Total annotations:", len(items))

names = [x.get("video_name") for x in items]
duplicate_count = len(names) - len(set(names))

print("Duplicate names:", duplicate_count)

FIELDS = [
    "intent_onset",
    "intervention_deadline",
    "pnr",
    "impact_outcome",
]

missing = []
invalid_order = []

for item in items:
    name = item.get("video_name")
    k = item.get("keyframes", {})

    try:
        times = [float(k[f]) for f in FIELDS]
    except (KeyError, TypeError, ValueError):
        missing.append(name)
        continue

    # Expected:
    # onset <= deadline <= PNR <= impact
    if times != sorted(times):
        invalid_order.append({
            "video": name,
            "times": times,
        })

print("Missing/invalid timestamps:", len(missing))
print("Invalid time ordering:", len(invalid_order))
print("Invalid examples:", invalid_order[:5])

distributions = {}

for key in [
    "danger_type",
    "severity",
    "reasoning_difficulty",
    "is_valid",
]:
    counts = Counter(
        str(item.get(key)) for item in items
    )
    distributions[key] = dict(counts)
    print(key, dict(counts))


# ==========================================================
# E0-C: Official evaluator compatibility
# ==========================================================

print("\n=== E0-C: EVALUATOR AUDIT ===")

eval_code = FILES["evaluator"].read_text()

schema = {
    "annotation_has_video_name": all(
        "video_name" in x for x in items
    ),
    "evaluator_uses_file_path":
        '"file_path"' in eval_code,
    "evaluator_expects_final_json":
        "anno_truth_final.json" in eval_code,
    "final_json_exists": (
        ROOT / "detector_dual_brain/anno_truth_final.json"
    ).is_file(),
}

for k, v in schema.items():
    print(k, v)


# ==========================================================
# E0-D: CPU compatibility
# ==========================================================

print("\n=== E0-D: CPU ENVIRONMENT ===")

modules = {}

for name in [
    "numpy",
    "cv2",
    "PIL",
    "torch",
    "transformers",
    "openai",
]:
    found = importlib.util.find_spec(name) is not None
    modules[name] = found
    print(name, "PASS" if found else "NOT INSTALLED")

torch_info = None

if modules["torch"]:
    import torch

    torch_info = {
        "version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
    }

    print("Torch:", torch_info)

print("Python:", sys.version.split()[0])

video_exts = {".mp4", ".avi", ".mkv", ".mov"}

videos = [
    p for p in ROOT.rglob("*")
    if p.is_file() and p.suffix.lower() in video_exts
]

print("Local video files:", len(videos))
print("Video examples:", [str(p) for p in videos[:5]])


# ==========================================================
# Save report
# ==========================================================

report = {
    "test": "HD-Guard E0",
    "scope": "official CPU-only source/data audit",
    "source_method": "GitHub Download ZIP + SCP",
    "source_zip_sha256": zip_sha256,
    "source_commit": None,
    "source_commit_verified": False,
    "metadata": metadata,
    "annotation_count": len(items),
    "duplicate_names": duplicate_count,
    "missing_timestamps": missing,
    "invalid_time_order": invalid_order,
    "distributions": distributions,
    "evaluator_schema": schema,
    "modules": modules,
    "torch": torch_info,
    "video_count": len(videos),
    "original_fastbrain_executed": False,
    "original_slowbrain_executed": False,
    "source_hashes": {
        key: hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for key, path in FILES.items()
    },
}

out = BASE / "e0_official_audit.json"

out.write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    )
)

print("\n=== E0 SUMMARY ===")
print("Annotations:", len(items))
print("Missing timestamps:", len(missing))
print("Invalid ordering:", len(invalid_order))
print("Local videos:", len(videos))
print("Saved:", out)
print("E0: AUDIT COMPLETE")
