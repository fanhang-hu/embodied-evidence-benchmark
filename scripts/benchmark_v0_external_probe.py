"""Evaluate external kitchen component on three captured relation observations.

Independent subprocess sees only the public objects projection and candidate.
This is offline authorization replay; it does not submit a Unity action.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'results/E6/38_benchmark_v0/run_20261122_01'
OUT = ROOT / 'results/benchmark_v0/external_probe_20261122_02'
ADAPTER = ROOT / 'scripts/benchmark_v0_external_kitchen_guard.py'
SOURCE = ROOT / 'external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise SystemExit('output already exists')
    manifest = json.loads((RUN / 'artifact_sha256.json').read_text())
    for path, expected in manifest.items():
        if sha(ROOT / path) != expected:
            raise RuntimeError('historical run artifact changed')
    lines = [json.loads(line) for line in (RUN / 'records.jsonl').read_text().splitlines() if line.strip()]
    inputs = []
    for index in lines:
        path = RUN / index['episode_file']
        if sha(path) != index['sha256']:
            raise RuntimeError('episode hash changed')
        row = json.loads(path.read_text())
        if row['family'] != 'relation' or row['arm'] != 'shared':
            continue
        steps = [step for step in row['steps'] if step['candidate']['action'] == 'ToggleObjectOn']
        if len(steps) != 1 or steps[0]['consumed_evidence']['channel'] != 'producer_stdout':
            raise RuntimeError('missing single public critical-action observation')
        step = steps[0]
        inputs.append((index, row, step))
    if {row['condition'] for _, row, _ in inputs} != {'benign_safe', 'clean_unsafe', 'producer_attack'} or len(inputs) != 3:
        raise RuntimeError('expected three shared relation observations')
    OUT.mkdir(parents=True)
    results = []
    for index, row, step in sorted(inputs, key=lambda x: x[1]['condition']):
        # Serialize only consumer-visible evidence; never pass evaluator labels,
        # submit truth, output directory, run files or case internals to Guard.
        public = {'action': step['candidate'], 'observation': {
            'objects': step['consumed_evidence']['payload']['objects']}}
        encoded = json.dumps(public, sort_keys=True, separators=(',', ':'), allow_nan=False)
        try:
            result = subprocess.run([sys.executable, '-B', str(ADAPTER)], input=encoded,
                                    text=True, capture_output=True, timeout=30, check=True)
            response = json.loads(result.stdout)
            state = 'COMPLETED'
        except (subprocess.SubprocessError, ValueError) as exc:
            response = None
            state = 'FAILED'
            error = type(exc).__name__
        # Evaluator checks target mapping and labels only after subprocess exit.
        if response is not None:
            details = response['details']
            target_match = (details.get('selected_knob_id') == row['case']['knob_id'] and
                            details.get('selected_burner_id') == row['case']['burner_id'])
            safety_label = bool(step['unsafe_candidate'])
            outcome = dict(condition=row['condition'], status=state, source_episode=index['episode_file'],
                           public_input_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
                           candidate=step['candidate'], native_guard_decision=response['native_guard_decision'],
                           target_mapping_matches_case=target_match, details=details, reason=response['reason'],
                           evaluator_unsafe_candidate=safety_label,
                           contract_comparable=False, contract_false_allow=None,
                           actual_execution=False)
        else:
            outcome = dict(condition=row['condition'], status=state, error_type=error,
                           source_episode=index['episode_file'], actual_execution=False)
        results.append(outcome)
        (OUT / (row['condition'] + '.json')).write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + '\n')
        print(row['condition'], state, outcome.get('native_guard_decision'), flush=True)
    summary = dict(status='OFFLINE_COMPONENT_PROBE_COMPLETE' if all(x['status'] == 'COMPLETED' for x in results) else 'INCOMPLETE',
                   episodes=len(results), native_runtime_episodes=0, model_calls=0,
                   source_sha256={'external_component': sha(SOURCE), 'adapter': sha(ADAPTER),
                                  'source_artifact_manifest': sha(RUN / 'artifact_sha256.json')},
                   limitations=['Offline replay of already observed shared relation traces',
                                'Original check component is not full controller including auto-redirection',
                                'Original policy is not the target-specific E6 relation contract',
                                'No external guard physical execution or official end-to-end reproduction',
                                'No claim that a deployed producer is attacker-accessible'],
                   results=results)
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    if summary['status'] != 'OFFLINE_COMPONENT_PROBE_COMPLETE':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
