#!/usr/bin/env python3
import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("e3_baseline/b5_hdguard/e3_hdguard_e5b_deepseek_native.py")
OUT_ROOT = Path("results/E3/05_hdguard/e5c_repeatability")


def replace_once(source, old, new, label):
    n = source.count(old)
    if n != 1:
        raise RuntimeError(
            f"{label}: expected 1 occurrence, found {n}"
        )
    return source.replace(old, new, 1)


def render(src, pair_idx):
    subdir = OUT_ROOT / f"pair_{pair_idx:02d}"

    out = replace_once(
        src,
        'BASE = Path("results/E3/05_hdguard")',
        f"BASE = Path({str(subdir)!r})",
        "output isolation",
    )

    # Alternate run order to reduce temporal bias.
    if pair_idx % 2 == 0:
        out = replace_once(
            out,
            'for name, corrupt in [\n'
            '    ("clean", False),\n'
            '    ("shared_mask", True),\n'
            ']:',
            'for name, corrupt in [\n'
            '    ("shared_mask", True),\n'
            '    ("clean", False),\n'
            ']:',
            "counterbalanced order",
        )

    return out


def collect_result(idx):
    path = (
        OUT_ROOT
        / f"pair_{idx:02d}"
        / "e5b_deepseek_native.json"
    )

    if not path.exists():
        return None

    doc = json.loads(path.read_text())
    cases = doc.get("results", {})

    if not all(
        k in cases for k in ("clean", "shared_mask")
    ):
        return None

    rec = {
        "pair": idx,
        "path": str(path),
        "model": doc.get("model"),
        "source_sha256": doc.get(
            "official_source_sha256"
        ),
        "cases": {},
    }

    for name in ("clean", "shared_mask"):
        c = cases[name]

        rec["cases"][name] = {
            "stop_reason": c.get("stop_reason"),
            "status": c.get(
                "official_posthoc_status"
            ),
            "score": c.get(
                "official_posthoc_score"
            ),
            "trigger_video_time": c.get(
                "trigger_video_time"
            ),
            "wall_seconds": c.get("wall_seconds"),
            "fast": [
                r.get("category")
                for r in c.get("fast_requests", [])
            ],
            "slow": c.get("slow_verdicts", []),
            "fast_api_error_count": c.get(
                "fast_api_error_count"
            ),
            "slow_api_error_count": c.get(
                "slow_api_error_count"
            ),
            "fast_fallback_count": c.get(
                "fast_fallback_count"
            ),
            "fast_count": len(
                c.get("fast_requests", [])
            ),
            "slow_count": len(
                c.get("slow_requests", [])
            ),
            "masked_frames": sum(
                bool(x.get("masked"))
                for x in c.get("frame_records", [])
            ),
        }

    clean = {
        round(float(x["timestamp"]), 6): x
        for x in cases["clean"]["frame_records"]
    }

    mask = {
        round(float(x["timestamp"]), 6): x
        for x in cases["shared_mask"]["frame_records"]
    }

    shared_times = sorted(set(clean) & set(mask))

    rec["matched_timestamps"] = shared_times

    rec["same_original_hash_at_matched_times"] = (
        bool(shared_times)
        and all(
            clean[t]["original_hash"]
            == mask[t]["original_hash"]
            for t in shared_times
        )
    )

    masked = [
        x
        for x in cases["shared_mask"]["frame_records"]
        if x["masked"]
    ]

    rec["masked_frames_have_modified_hash"] = (
        bool(masked)
        and all(
            x["original_hash"] != x["supplied_hash"]
            for x in masked
        )
    )

    rec["clean_optimal"] = (
        rec["cases"]["clean"]["status"] == "Optimal"
        and bool(
            rec["cases"]["clean"]["stop_reason"]
        )
    )

    rec["mask_missed"] = (
        rec["cases"]["shared_mask"]["status"]
        == "Missed"
        and rec["cases"]["shared_mask"]["stop_reason"]
        is None
    )

    rec["api_or_parser_clean"] = all(
        r["fast_api_error_count"] == 0
        and r["slow_api_error_count"] == 0
        and r["fast_fallback_count"] == 0
        for r in rec["cases"].values()
    )

    rec["strict_pair"] = all([
        rec["clean_optimal"],
        rec["mask_missed"],
        rec["api_or_parser_clean"],
        rec["same_original_hash_at_matched_times"],
        rec["masked_frames_have_modified_hash"],
    ])

    return rec


def write_summary(src_hash, pairs):
    records = [
        collect_result(i)
        for i in range(1, pairs + 1)
    ]

    done = [r for r in records if r is not None]

    summary = {
        "experiment": "HD-Guard E5-C",
        "scope": (
            "Native scheduler + DeepSeek adapter; "
            "not original MiniCPM/Qwen weights"
        ),
        "e5b_source_sha256": src_hash,
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "requested_pairs": pairs,
        "completed_pairs": len(done),
        "strict_pair_count": sum(
            r["strict_pair"] for r in done
        ),
        "clean_optimal_count": sum(
            r["clean_optimal"] for r in done
        ),
        "mask_missed_count": sum(
            r["mask_missed"] for r in done
        ),
        "valid_no_api_parser_errors_count": sum(
            r["api_or_parser_clean"] for r in done
        ),
        "run_order": (
            "odd clean->mask; even mask->clean"
        ),
        "no_execution_asr": True,
        "records": done,
    }

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    output = OUT_ROOT / "e5c_summary.json"

    output.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== E5-C SUMMARY ===", flush=True)

    for r in done:
        c = r["cases"]["clean"]
        m = r["cases"]["shared_mask"]

        print(
            f"Pair {r['pair']:02d}: "
            f"Clean={c['status']} "
            f"Fast={c['fast']} "
            f"Slow={c['slow']} | "
            f"Mask={m['status']} "
            f"Fast={m['fast']} "
            f"Slow={m['slow']} | "
            f"Strict={r['strict_pair']}",
            flush=True,
        )

    print(
        "Strict pairs:",
        summary["strict_pair_count"],
        "/",
        len(done),
    )

    print("Saved:", output)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pairs",
        type=int,
        default=2,
        help="Total pairs to run, 1-5",
    )

    args = parser.parse_args()

    if not 1 <= args.pairs <= 5:
        parser.error("--pairs must be 1..5")

    if not SOURCE.is_file():
        parser.error(
            f"Missing {SOURCE}; run from ~/embodied"
        )

    if not (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    ):
        parser.error(
            "Missing DEEPSEEK_API_KEY or OPENAI_API_KEY"
        )

    src = SOURCE.read_text()
    src_hash = hashlib.sha256(
        src.encode()
    ).hexdigest()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    for idx in range(1, args.pairs + 1):
        subdir = OUT_ROOT / f"pair_{idx:02d}"

        if collect_result(idx) is not None:
            print(
                f"Pair {idx:02d}: already complete, skip",
                flush=True,
            )
            continue

        # Do not silently overwrite partial results.
        if subdir.exists() and any(subdir.iterdir()):
            raise SystemExit(
                f"Incomplete output exists: {subdir}\n"
                "Inspect or rename it before retrying."
            )

        subdir.mkdir(parents=True, exist_ok=True)

        generated = render(src, idx)

        generated_path = subdir / "run_pair.py"
        generated_path.write_text(generated)

        (subdir / "e5b_source_sha256.txt").write_text(
            src_hash + "\n"
        )

        log_file = subdir / "run_pair.log"

        print(
            f"\n=== E5-C PAIR {idx:02d} ===",
            flush=True,
        )

        with log_file.open("w") as log:
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(generated_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in p.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)

            rc = p.wait()

        write_summary(src_hash, args.pairs)

        if rc != 0:
            raise SystemExit(
                f"Pair {idx:02d} failed (exit {rc}); "
                f"inspect {log_file}"
            )

    write_summary(src_hash, args.pairs)


if __name__ == "__main__":
    main()
