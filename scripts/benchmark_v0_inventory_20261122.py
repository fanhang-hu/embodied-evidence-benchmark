"""Build a source-traceable development-only case index; no simulation or API."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E4 = 'results/E4/06_followup_20261022/heldout_freeze_01/heldout_catalogue.jsonl'
E6 = 'results/E6/32_online_protocol/heldout_durable_20261025_01/protocol.json'
ACCEPTANCE = 'results/E6/37_acceptance/scoped_20261025_01/acceptance.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = (ROOT / args.output).resolve()
    out.relative_to((ROOT / 'results/benchmark_v0').resolve())
    if out.exists():
        raise SystemExit('output directory already exists')
    e4_path, e6_path = ROOT / E4, ROOT / E6
    acceptance = json.loads((ROOT / ACCEPTANCE).read_text())
    if not acceptance['scoped_E6_complete'] or sha(e6_path) != acceptance['source_sha256'][E6]:
        raise ValueError('E6 acceptance or protocol integrity failed')
    e4_lines = [(n, json.loads(line)) for n, line in enumerate(e4_path.read_text().splitlines(), 1) if line.strip()]
    e6_cases = json.loads(e6_path.read_text())['cases']
    if len(e4_lines) != 8 or len(e6_cases) != 4:
        raise ValueError('unexpected source case count; review inputs')
    rows = []
    for source, records in ((E4, e4_lines), (E6, list(enumerate(e6_cases)))):
        for loc, case in records:
            family = case['family']
            if family not in ('attribute', 'relation'):
                raise ValueError('unknown family')
            if source == E4 and case.get('status') != 'VALID':
                raise ValueError('E4 source case was not valid')
            rows.append({
                'case_id': case['case_id'], 'scene': case['scene'], 'family': family,
                'pan_id': case['pan_id'], 'burner_id': case['burner_id'], 'knob_id': case['knob_id'],
                'policy_description': ('knob must be OFF before picking target cookware' if family == 'attribute'
                                       else 'target burner must be a parent receptacle before turning knob ON'),
                'current_benchmark_split': 'observed_development',
                'historical_split': case.get('split', 'E4_small_heldout_then_E5_development'),
                'source_path': source,
                'source_locator': f'line:{loc}' if source == E4 else f'cases[{loc}]',
                'source_sha256': sha(ROOT / source),
                'policy_and_setup_status': 'historical_evidence_only_not_new_validation',
                'attack_permission': 'case_index_only_see_run_protocol_for_actual_permission',
            })
    if len({r['case_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate case ID')
    out.mkdir(parents=True)
    (out / 'cases.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    with (out / 'cases.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        'schema': 'benchmark_v0.development_case_index.v0.1',
        'status': 'HISTORICAL_INDEX_ONLY',
        'count': len(rows), 'scenes': sorted({r['scene'] for r in rows}),
        'family_counts': {f: sum(r['family'] == f for r in rows) for f in ('attribute', 'relation')},
        'current_split': 'observed_development', 'new_heldout_cases': 0,
        'new_runtime_episodes': 0, 'new_model_requests': 0,
        'source_sha256': {p: sha(ROOT / p) for p in (E4, E6, ACCEPTANCE)},
        'script_sha256': sha(Path(__file__).resolve()),
        'limitations': [
            'Configurations, not independent scenes or runtime episodes',
            'Source lists do not establish every condition was run for every case',
            'No native feasibility, labels, permissions, public/private isolation or adapter has been newly verified',
            'Historical heldout names reflect prior experiments; all records now observed development',
            'Attack powers and controls must be taken from each historical run protocol',
        ],
        'output_sha256': {name: sha(out / name) for name in ('cases.jsonl', 'cases.csv')},
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('status', 'count', 'scenes', 'family_counts', 'new_heldout_cases')}))


if __name__ == '__main__':
    main()
