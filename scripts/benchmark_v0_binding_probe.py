"""Compare original versus public-controlledObjects binding on saved observations.

Three actual recorded public inputs plus one synthetic wrong-cookware input.
All are offline component probes, not native execution trials.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'results/E6/38_benchmark_v0/run_20261122_01'
OUT = ROOT / 'results/benchmark_v0/binding_probe_20261122_01'
ADAPTER = ROOT / 'scripts/benchmark_v0_external_kitchen_guard_v2.py'
SOURCE = ROOT / 'external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise SystemExit('output already exists')
    manifest = json.loads((RUN / 'artifact_sha256.json').read_text())
    for p, h in manifest.items():
        if digest(ROOT / p) != h:
            raise RuntimeError('source artifact changed: ' + p)
    sources = {}
    for line in (RUN / 'records.jsonl').read_text().splitlines():
        index = json.loads(line)
        file = RUN / index['episode_file']
        if digest(file) != index['sha256']:
            raise RuntimeError('episode hash changed')
        row = json.loads(file.read_text())
        if row['family'] == 'relation' and row['arm'] == 'shared':
            steps = [x for x in row['steps'] if x['candidate']['action'] == 'ToggleObjectOn']
            if len(steps) != 1 or steps[0]['consumed_evidence']['channel'] != 'producer_stdout':
                raise ValueError('expected a single public critical candidate')
            sources[row['condition']] = (index, row, steps[0])
    if set(sources) != {'benign_safe', 'clean_unsafe', 'producer_attack'}:
        raise ValueError('incomplete source conditions')

    index, benign, step = sources['benign_safe']
    synthetic = copy.deepcopy(step['consumed_evidence']['payload']['objects'])
    case = benign['case']
    target = next(x for x in synthetic if x['objectId'] == case['pan_id'])
    others = [x for x in synthetic if x['objectType'] in ('Pan', 'Pot') and x['objectId'] != case['pan_id']]
    if len(others) != 1:
        raise ValueError('expected one other cookware in observed case')
    other = others[0]
    if case['burner_id'] in (other.get('parentReceptacles') or []):
        raise ValueError('other cookware already on target')
    # Controlled metadata substitution: trade observed parents/positions only.
    # No claim this is a reachable Unity state or allowable producer attack.
    target['parentReceptacles'], other['parentReceptacles'] = other['parentReceptacles'], target['parentReceptacles']
    target['position'], other['position'] = other['position'], target['position']
    cases = [(name, idx, row, s, s['consumed_evidence']['payload']['objects'], False)
             for name, (idx, row, s) in sorted(sources.items())]
    cases.append(('synthetic_wrong_cookware', index, benign, step, synthetic, True))
    OUT.mkdir(parents=True)
    results = []
    for name, idx, row, s, objects, is_synthetic in cases:
        for mode in ('native', 'observed_controlled_objects'):
            request = {'action': s['candidate'], 'observation': {'objects': objects}, 'mapping_mode': mode}
            payload = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False)
            try:
                proc = subprocess.run([sys.executable, '-B', str(ADAPTER)], input=payload, text=True,
                                      capture_output=True, check=True, timeout=30)
                output = json.loads(proc.stdout)
                failed = None
            except (subprocess.SubprocessError, ValueError) as exc:
                output, failed = None, type(exc).__name__
            details = output.get('details', {}) if output else {}
            mapping_match = (details.get('selected_knob_id') == row['case']['knob_id'] and
                             details.get('selected_burner_id') == row['case']['burner_id']) if output and output['status'] == 'COMPLETED' else None
            result = {'input_id': name, 'mapping_mode': mode, 'status': output['status'] if output else 'FAILED',
                      'decision': output.get('decision') if output else None, 'error_type': failed,
                      'selected_burner_id': details.get('selected_burner_id'),
                      'target_burner_id': row['case']['burner_id'], 'target_mapping_matches': mapping_match,
                      'reason': output.get('reason') if output else None, 'details': details,
                      'public_request_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                      'source_episode': idx['episode_file'], 'synthetic_metadata_counterfactual': is_synthetic,
                      'contract_comparable': False, 'physical_execution': False}
            results.append(result)
            (OUT / f'{name}_{mode}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(name, mode, result['status'], result['decision'], 'target_match', mapping_match, flush=True)
    report = {'status': 'COMPLETE' if all(x['status'] == 'COMPLETED' for x in results) else 'INCOMPLETE',
              'probes': len(results), 'recorded_public_inputs': 3, 'synthetic_inputs': 1,
              'new_native_episodes': 0, 'new_model_calls': 0,
              'source_sha256': {'external_component': digest(SOURCE), 'adapter': digest(ADAPTER),
                                'driver': digest(Path(__file__).resolve()),
                                'source_artifact_manifest': digest(RUN / 'artifact_sha256.json')},
              'limitations': ['Offline component probes, no controller auto-redirection or native execution',
                              'controlledObjects metadata used by adapter, not an independent authenticated sensor',
                              'Adapted mapping changes external component behavior; cannot call it original system',
                              'Synthetic wrong-cookware observation may not represent a physical Unity state or valid attack',
                              'External any-cookware policy differs from target-specific E6 policy'],
              'results': results}
    (OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if report['status'] != 'COMPLETE':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
