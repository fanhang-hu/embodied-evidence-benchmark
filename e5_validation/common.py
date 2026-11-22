"""Shared evidence I/O and prospective protocol checks, with no model calls."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = Path("results/E4/06_followup_20261022/heldout_freeze_01/heldout_catalogue.jsonl")
WRONG_BURNER = CATALOGUE.with_name("wrong_burner.jsonl")
FREEZE = Path("results/E5/00_protocol/freeze_20261023_02")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def append_jsonl(path, value):
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()


def write_csv(path, rows):
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def new_output(path):
    path = Path(path).resolve()
    require(path.is_relative_to(ROOT / "results/E5") and not path.exists(),
            "Output must be a NEW directory under results/E5")
    path.mkdir(parents=True, exist_ok=False)
    return path


def check_freeze(freeze=FREEZE, *, archived=False):
    freeze = ROOT / freeze
    manifest = read_json(freeze / "manifest.json")
    for name, expected in manifest["source_sha256"].items():
        path = ROOT / name
        if file_sha(path) != expected and archived:
            path = freeze / "frozen_sources" / name
        require(path.is_file() and file_sha(path) == expected, f"Frozen E5 input/source changed: {name}")
    cases = read_jsonl(ROOT / CATALOGUE)
    require([c["case_id"] for c in cases] == manifest["case_ids"], "Case selection changed")
    return manifest, cases


def finish_hashes(out):
    write_json(out / "artifact_sha256.json", {
        str(p.relative_to(ROOT)): file_sha(p) for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "artifact_sha256.json"})


def state(items, version=0):
    return dict(schema="e5.observation.v1", source_id="T0_E5_adapter", state_version=version, objects=items)


def evidence_row(evidence_id, case, episode, state_hash, path, producer, parents,
                 *, allowed, trust, collected=None, version=0, fields=()):
    """No invented historical timestamps, cryptographic identity or independence."""
    return dict(evidence_id=evidence_id, scene_id=case["scene"], episode_id=episode,
                object_id=case["pan_id"], target_id=case["burner_id"],
                predicate="bound_power_off" if case["family"] == "attribute" else "cookware_on_exact_burner",
                value="see_snapshot", snapshot_sha256=state_hash, snapshot_path=path,
                producer_id=producer, parent_source_ids=parents,
                collection_monotonic_ns=collected, received_monotonic_ns=collected,
                manifest_registered_monotonic_ns=time.perf_counter_ns(),
                timestamp_semantics="Python adapter snapshot capture/receipt; native sensor timestamp unavailable; archive timestamps null",
                validity_interval_ns=None, state_version=version,
                observation_type="native_metadata" if trust == "X_protected_native" else "serialized_metadata",
                image_sha256=None, attackable_fields=list(fields), attacker_level="T0",
                evidence_trust=trust, observability="predicate_metadata_present",
                allowed_to_defender=allowed, source_traceable=True, cryptographic_authentication=False,
                uncorrupted_under_threat_model=trust == "X_protected_native",
                sufficiency="evaluated_separately_not_implied_by_traceability",
                private_evaluator_truth="SEPARATE_FILE_NEVER_IN_MODEL_PROMPT")
