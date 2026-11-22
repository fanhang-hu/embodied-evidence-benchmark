#!/usr/bin/env python3
"""Inspect historical baseline compatibility without treating missing results as zero."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "benchmark_v0/spec/historical_baselines.v1.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", choices=("relation", "attribute"))
    parser.add_argument("--json", action="store_true", help="print the machine-readable records")
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    records = catalog["baselines"]
    if len(records) != 9 or {r["number"] for r in records} != set(range(1, 10)):
        raise SystemExit("Catalog must contain the nine distinct historical entries")
    allowed = {"ADAPTED_EVALUATED", "NOT_INTEGRATED"}
    for record in records:
        if set(record["contracts"]) != {"relation", "attribute"}:
            raise SystemExit(f"Incomplete contract coverage: {record['name']}")
        if not set(record["contracts"].values()) <= allowed:
            raise SystemExit(f"Unknown status: {record['name']}")
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return
    print("# Historical baseline compatibility\n")
    print("ADAPTED_EVALUATED is a scoped adaptation; NOT_INTEGRATED is not a measured zero.\n")
    columns = [args.contract] if args.contract else ["relation", "attribute"]
    print("| # | Baseline | " + " | ".join(columns) + " | Scope |")
    print("|---|---|" + "---|" * len(columns) + "---|")
    for r in records:
        statuses = " | ".join(r["contracts"][c] for c in columns)
        print(f"| {r['number']} | {r['name']} | {statuses} | {r['scope']} |")


if __name__ == "__main__":
    main()
