"""Supplement prior native audits with complete sequence/source/timing checks."""
import argparse

from e5_validation.common import ROOT, file_sha, finish_hashes, read_json, write_json
from e6_validation.evidence_checks import verify_episode
from e6_validation.producer_audit import require
from e6_validation.producer_experiment import new_directory
from e6_validation.runtime_v3 import load_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", action="append", nargs=2, required=True, metavar=("RUN", "PRIOR_AUDIT"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    results = []
    for relative, audit_relative in args.track:
        run, audit_path = ROOT / relative, ROOT / audit_relative
        prior = read_json(audit_path)
        require(prior["status"] == "PASS_NATIVE_CUSTOM_PIPELINE" and prior["source_run"] == relative,
                "Missing matching prior native audit")
        for path, expected in read_json(run / "artifact_sha256.json").items():
            require(file_sha(ROOT / path) == expected, "Prior artifact changed")
        rows = load_rows(run)
        require(len(rows) == prior["audited"], "Prior audit count changed")
        for row in rows:
            verify_episode(row)
        results.append(dict(run=relative, prior_audit=audit_relative, prior_audit_sha256=file_sha(audit_path),
                            artifacts_sha256=file_sha(run / "artifact_sha256.json"), audited=len(rows)))
        print(relative, len(rows), "PASS", flush=True)
    out = new_directory(args.out)
    write_json(out / "audit.json", dict(status="PASS_SUPPLEMENTAL_TRACE_AUDIT", tracks=results,
        audited=sum(r["audited"] for r in results), original_E6_complete=False,
        source_sha256={p: file_sha(ROOT / p) for p in
                       ("e6_validation/evidence_checks.py", "e6_validation/trace_audit.py")},
        checks=["No unexplained plan truncation or execution after a terminal decision",
                "Planner/Monitor inputs bound to accounted Producer publications",
                "Same-source/protected Fresh queries occur within the current authorization interval",
                "Agent native receipts match submission logs; final policy facts match last recorded state",
                "Evaluator relation drift has its expected unforced native pickup receipt"],
        limitations=["Supplement to prior audits; not new native executions or independent trials",
                     "Stored evidence cannot establish authenticity against a compromised evaluator",
                     "No concurrency, silent notification loss or atomic execution guarantee"] ))
    finish_hashes(out)


if __name__ == "__main__":
    main()
