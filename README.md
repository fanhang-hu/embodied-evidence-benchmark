# Embodied Evidence Benchmark (development)

An early research benchmark for whether an embodied agent's safety authorization remains reliable when a low-trust environment evidence producer can report corrupted state. This repository snapshot contains the project's own development code, research notes, and selected aggregate results.

The present system is a prototype, **not** a completed held-out benchmark. The observed attacks use a custom confined Producer and do not claim a vulnerability in native AI2-THOR or SafeAgentBench. Results and current limitations are summarized in [the research overview](share-pool/embodied-1122.md) and [E1–E6 report](share-pool/截至2026-10-26实验总报告-E1至E6与九项Baseline.md).

## Current coverage

- Two minimal safety contracts: cookware on a designated burner before switching it on, and a designated stove knob being off before pickup.
- Fixed-candidate Unity execution, restricted evidence mutation, authorization decisions, isolated Guard processes, native execution receipts and private evaluator truth.
- Controls for shared evidence, same-source refresh where implemented, protected controller queries, and fail-closed. An adapted external kitchen component is evaluated only on a compatible contract; it is not a complete replication of its official agent.
- Development-only attribute evaluation can select existing cases in one command; see [four-scene report](share-pool/benchmark-V0-属性合同四场景与简化运行-2026-11-22.md).

Results must be reported by contract, method, condition and actual denominator. Do not treat the different contracts or their implementations as a single pooled success rate. The nine historical baseline investigations are documented in [the baseline appendix](share-pool/九项Baseline历史实验明细附录-2026-10-26.md); they are not all integrated into the current runner.

## Snapshot and reproducibility

This is the first Git snapshot of files from the working directory. The source directory did not expose usable Git history, so this commit does **not** reconstruct past commits; earlier experiment versions and reports are retained as files. Selected aggregate summaries and their original workspace paths and SHA-256 hashes are in `evidence/summaries/`.

This snapshot intentionally omits the multi-gigabyte `results/` and `external/` directories, raw evaluator truth, full traces, model credentials, simulator binaries and third-party repositories. Consequently, many scripts and tests that refer to historical run artifacts, frozen catalogues, or external source trees will not run from this snapshot alone. Restore those assets from the original workspace or obtain each upstream dependency under its own terms; check provenance, licenses, access rights and privacy before sharing. The exact local paths and AI2-THOR Unity release are environment-specific. A tested machine used Python 3.10 and AI2-THOR 5.0.0, but this is not yet a portable installation specification.

Evaluation records and full truth snapshots belong to the evaluator, not to the Guard. Treat unpublished results, private traces and credentials as private until separately reviewed.

## Layout

- `benchmark_v0/spec/`: development contracts, schemas and method capability cards.
- `scripts/benchmark_v0_*`: runners, adapters, auditors and result exporters.
- `e1_validation/` through `e6_validation/`: historical experiment implementations.
- `e3_baseline/`: historical baseline integrations and research adaptations.
- `tests/`: development tests, some of which require omitted historical artifacts.
- `share-pool/`: research reports and experiment notes.
- `evidence/summaries/`: selected aggregate summaries; not the full experiment archive.

Version code and ordinary development in Git. Before a formal final test, record the selected cases, methods, permissions, source revision and budget before inspecting results; routine development does not require a separate frozen directory for every change.
