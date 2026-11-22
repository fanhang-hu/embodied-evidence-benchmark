#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
from pathlib import Path

from huggingface_hub import (
    HfApi,
    hf_hub_download,
    snapshot_download,
)

REPO = "EMBGuard/EMBGuard-2B"
REVISION = "4f9a4f4f7a15a00da836085d8ccb10c6448f23b7"
DEST = _bootstrap.ROOT / "external/EMBGuard-2B"

ROOT_EXTENSIONS = {
    ".safetensors",
    ".json",
    ".txt",
    ".model",
    ".jinja",
    ".tiktoken",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--step",
        required=True,
        choices=["list", "probe", "download"],
    )
    args = parser.parse_args()

    api = HfApi()
    info = api.model_info(
        REPO,
        revision=REVISION,
        files_metadata=True,
    )

    if info.sha != REVISION:
        raise RuntimeError(
            f"Unexpected revision: {info.sha}"
        )

    items = {
        item.rfilename: item
        for item in info.siblings
    }

    selected = sorted(
        name
        for name in items
        if "/" not in name
        and Path(name).suffix in ROOT_EXTENSIONS
    )

    if not {"config.json", "model.safetensors"}.issubset(
        selected
    ):
        raise RuntimeError(
            "Expected runtime files not found"
        )

    print("REPO:", REPO, flush=True)
    print("REVISION:", info.sha, flush=True)
    print("\nSelected root-level files:", flush=True)

    for name in selected:
        print(
            name,
            getattr(items[name], "size", None),
            flush=True,
        )

    if args.step == "list":
        return

    DEST.mkdir(parents=True, exist_ok=True)

    if args.step == "probe":
        probe_name = (
            "tokenizer.json"
            if "tokenizer.json" in selected
            else "config.json"
        )

        p = hf_hub_download(
            repo_id=REPO,
            filename=probe_name,
            revision=REVISION,
            local_dir=DEST,
            etag_timeout=30,
        )

        print(
            "PROBE PASS:",
            p,
            Path(p).stat().st_size,
            flush=True,
        )
        return

    path = Path(
        snapshot_download(
            repo_id=REPO,
            revision=REVISION,
            local_dir=DEST,
            allow_patterns=selected,
            max_workers=2,
            etag_timeout=30,
        )
    )

    missing = [
        name for name in selected
        if not (path / name).is_file()
    ]

    if missing:
        raise RuntimeError(
            f"Missing files: {missing}"
        )

    model_file = path / "model.safetensors"
    actual = model_file.stat().st_size
    expected = getattr(
        items["model.safetensors"],
        "size",
        None,
    )

    if expected is not None and actual != expected:
        raise RuntimeError(
            f"Weight size mismatch: {actual} != {expected}"
        )

    if actual < 3_500_000_000:
        raise RuntimeError(
            f"Suspiciously small weight: {actual}"
        )

    from safetensors import safe_open

    with safe_open(
        str(model_file),
        framework="pt",
        device="cpu",
    ) as f:
        names = list(f.keys())

    print("\nDOWNLOAD COMPLETE:", path, flush=True)
    print("MODEL BYTES:", actual, flush=True)
    print("SAFETENSORS KEYS:", len(names), flush=True)
    print("EMBGUARD E3D DOWNLOAD AND HEADER CHECK PASS")


if __name__ == "__main__":
    main()
