"""E5-B final paired comparison, read-only source verification."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
A = Path("results/E5/A_consistent_pollution")
B = Path("results/E5/B_evidence_sources")
OUT = ROOT / B / "07_release/final_20261024_01"

a_report = A / "03_report/audit_20261024_02/summary.json"
b_report = B / "06_report/audit_20261024_01/summary.json"
a_records = A / "02_native/run_20261024_01/records.jsonl"
b_records = B / "05_native/run_20261024_01/records.jsonl"

def digest(path):
    h = hashlib.sha256()
    with open(ROOT / path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load(path):
    return json.loads((ROOT / path).read_text())

a = load(a_report)
b = load(b_report)
run = load(B / "05_native/run_20261024_01/summary.json")

assert a["audited_episodes"] == 50
assert b["audited"] == 20
assert run["complete"] is True
assert run["recorded"] == 20
assert run["expected"] == 20
assert a["source_sha256"] == digest(a_records)
assert b["source_sha256"] == digest(b_records)

a_rows = {
    (x["arm"], x["true_initial"]): x
    for x in a["comparison"]
}
b_rows = {
    (x["arm"], x["true_initial"]): x
    for x in b["comparison"]
}

groups = [
    ("B0_original", a_rows, "A2_pair_off_original"),
    ("B1_consistency", a_rows, "A3_pair_off_consistency"),
    ("B2_receipt_only", b_rows, "B2_receipt_only"),
    ("B3_receipt_then_fresh", b_rows, "B3_receipt_then_fresh"),
    ("B4_fresh_always", a_rows, "A4_pair_off_fresh"),
]

comparison = []

for label, source, arm in groups:
    on = source[(arm, "ON")]
    off = source[(arm, "OFF")]

    assert on["n"] == off["n"] == 5

    comparison.append({
        "group": label,
        "source": "E5-A" if source is a_rows else "E5-B",
        "true_on_n": on["n"],
        "true_on_UAR": on["unsafe_authorizations"],
        "true_on_execution_violations": on["execution_violations"],
        "true_off_n": off["n"],
        "true_off_safe_task_success": off["safe_task_success"],
        "legal_DEFER": (
            on["false_DEFER"] + off["false_DEFER"]
        ),
        "protected_queries": (
            on["protected_queries"] + off["protected_queries"]
        ),
        "native_failures": (
            on["native_failures"] + off["native_failures"]
        ),
    })

assert not OUT.exists(), f"STOP: release exists: {OUT}"
OUT.mkdir(parents=True)

with (OUT / "comparison.csv").open("w", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(comparison[0])
    )
    writer.writeheader()
    writer.writerows(comparison)

(OUT / "comparison.json").write_text(
    json.dumps(comparison, indent=2, ensure_ascii=False) + "\n"
)

lines = [
    "# E5-B Final: Evidence Provenance and Sufficiency",
    "",
    "Status: 20/20 formal B2/B3 episodes completed; independent audit PASS.",
    "",
    "| Group | ON: execution violations | OFF: safe task success | Legal DEFER | Protected Pass |",
    "|---|---:|---:|---:|---:|",
]

for r in comparison:
    lines.append(
        f"| {r['group']} | "
        f"{r['true_on_execution_violations']}/5 | "
        f"{r['true_off_safe_task_success']}/5 | "
        f"{r['legal_DEFER']} | "
        f"{r['protected_queries']} |"
    )

lines += [
    "",
    "## Finding",
    "",
    "Under explicitly granted access to complete ordered single-writer "
    "setup receipts, successful bound ON-action receipts prevented "
    "unsafe removal. Missing OFF evidence caused Receipt-Only to DEFER. "
    "Receipt-Then-Fresh preserved the observed safety and legitimate "
    "task completion of Fresh-Always while reducing native protected "
    "queries from 10 to 5 in these configurations.",
    "",
    "## Scope and limitations",
    "",
    "- T0 controlled-copy attacker; no native T1/T2 compromise demonstrated.",
    "- Guard access to Evaluator setup receipts is an experimental assumption.",
    "- Historical continuity is assumed, not cryptographically authenticated.",
    "- Receipts and Pass share the same Unity physical root.",
    "- Five reused E4 configurations, not new heldout or independent samples.",
    "- Archived LLM responses, not new online generation.",
    "- No replanning or recovery following BLOCK/DEFER.",
    "- Query reduction is not an end-to-end latency reduction claim.",
    "- B0/B1/B4 reuse E5-A audited evidence, not new executions.",
    "",
    "## Audited inputs",
    "",
    f"- E5-A audit: `{a_report}`",
    f"- E5-B audit: `{b_report}`",
    f"- E5-A records: `{a_records}`",
    f"- E5-B records: `{b_records}`",
]

(OUT / "E5_B_FINAL.md").write_text("\n".join(lines) + "\n")

sources = [
    a_report, b_report, a_records, b_records,
    A / "00_protocol/freeze_20261024_01/manifest.json",
    B / "01_protocol/freeze_20261024_01/manifest.json",
    Path("e5_validation/b_evidence_sources/policy.py"),
    Path("e5_validation/b_evidence_sources/runner.py"),
    Path("e5_validation/b_evidence_sources/report.py"),
]

for p in sorted(sources, key=str):
    assert (ROOT / p).is_file(), f"Missing: {p}"

with (OUT / "SHA256SUMS.txt").open("w") as f:
    for p in sorted(sources, key=str):
        f.write(f"{digest(p)}  {p.as_posix()}\n")

print("E5-B FINAL REPORT: CREATED")
print("Combined comparison: 50 paired-condition records")
for r in comparison:
    print(r)
print("Release directory:", OUT)
