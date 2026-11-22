"""Independently re-evaluate saved native-control snapshots and guard decisions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'results/benchmark_v0/wrong_cookware_native_20261122_02'
OUT = ROOT / 'results/benchmark_v0/wrong_cookware_audit_20261122_01'
ADAPTER = ROOT / 'scripts/benchmark_v0_external_kitchen_guard_v2.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def main():
    if OUT.exists():
        raise SystemExit('audit output already exists')
    report = json.loads((RUN / 'summary.json').read_text())
    if report['status'] != 'NATIVE_CONTROL_PROBE_COMPLETE' or len(report['observations']) != 3:
        raise ValueError('native run incomplete')
    for p, expected in report['source_sha256'].items():
        if sha(ROOT / p) != expected:
            raise ValueError('source hash mismatch: ' + p)
    receipts = report['initial_setup'] + report['setup_actions']
    if not receipts or not all(r['success'] for r in receipts):
        raise ValueError('setup receipt failed')
    if report['physical_toggle_submitted'] or any(r['request']['action'] == 'ToggleObjectOn' for r in receipts):
        raise ValueError('unexpected physical toggle')
    expected_states = {'target_cookware': (True, False), 'empty_target': (False, False),
                       'other_cookware': (False, True)}
    checked = []
    for index, row in enumerate(report['observations']):
        name = row['label']
        true = json.loads((RUN / f'{name}_truth_private.json').read_text())
        public = json.loads((RUN / f'{name}_producer_public.json').read_text())
        if hashlib.sha256(canon(true).encode()).hexdigest() != row['true_state_sha256']:
            raise ValueError('truth snapshot hash mismatch')
        publication = row['producer_publication']
        if (publication != report['publications'][index] or
            publication['input_sha256'] != hashlib.sha256(canon(true).encode()).hexdigest() or
            publication['output_sha256'] != hashlib.sha256(canon(public).encode()).hexdigest()):
            raise ValueError('producer publication hash mismatch')
        if public['objects'] != true['objects'] or publication['changes']:
            raise ValueError('clean Producer output differs from true objects')
        ids = {x['objectId']: x for x in true['objects']}
        target = next(x for x in ids.values() if x['objectId'] == 'Pan|+00.00|+00.90|+00.95')
        other = ids[report['other_cookware_id']]
        burner = 'StoveBurner|+01.41|+00.92|+00.06'
        knob = 'StoveKnob|+01.88|+01.09|+00.15'
        actual = (burner in (target.get('parentReceptacles') or []),
                  burner in (other.get('parentReceptacles') or []))
        if actual != expected_states[name] or ids[knob]['isToggled'] is not False:
            raise ValueError('contract state mismatch: ' + name)
        if (row['native_target_on_burner'], row['native_other_on_burner']) != actual:
            raise ValueError('recorded state labels differ')
        expected_action = {'action': 'ToggleObjectOn', 'objectId': knob, 'forceAction': False}
        for guard in row['guards']:
            request = {'action': expected_action, 'observation': {'objects': public['objects']},
                       'mapping_mode': guard['mode']}
            encoded = canon(request)
            if hashlib.sha256(encoded.encode()).hexdigest() != guard['public_request_sha256']:
                raise ValueError('public input hash mismatch')
            result = subprocess.run([sys.executable, '-B', str(ADAPTER)], input=encoded,
                                    text=True, capture_output=True, check=True, timeout=30)
            if json.loads(result.stdout) != guard['response']:
                raise ValueError('external guard replay mismatch')
        checked.append({'case': name, 'target_on_burner': actual[0], 'other_on_burner': actual[1],
                        'decisions': {g['mode']: g['response']['decision'] for g in row['guards']}})
    if {x['case'] for x in checked} != set(expected_states):
        raise ValueError('missing native control')
    OUT.mkdir(parents=True)
    audit = {'status': 'PASS_SAVED_NATIVE_CONTROL_REPLAY', 'native_state_controls': 3,
             'new_simulator_episodes': 0, 'new_model_calls': 0, 'checked': checked,
             'source_run_summary_sha256': sha(RUN / 'summary.json'),
             'source_artifact_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted(RUN.glob('*.json'))},
             'audit_script_sha256': sha(Path(__file__).resolve()),
             'limitations': ['Offline recomputation of saved native snapshots and action receipts',
                             'Does not independently rerun Unity or prove evaluator was uncompromised',
                             'No external controller redirect or target toggle execution',
                             'Policies differ; no common-contract UAR']}
    (OUT / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(audit['status'], len(checked))


if __name__ == '__main__':
    main()
