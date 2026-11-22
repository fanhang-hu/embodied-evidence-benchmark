"""Run the E6-based development benchmark prototype (no online API calls).

The frozen E6 driver, protocol format, producer and audits are used unchanged.
Outputs are placed in fresh results/E6/38_benchmark_v0/<stage>_<name>/ directories.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('results/E6/38_benchmark_v0')
CASES = ('attribute_FloorPlan6_03', 'relation_FloorPlan6_02')
ARMS = ('shared', 'same_source_fresh', 'critical_only_fresh', 'fail_closed')
CONDITIONS = ('benign_safe', 'clean_unsafe', 'producer_attack')


def call(module: str, *args: str) -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', LIBGL_ALWAYS_SOFTWARE='1')
    subprocess.run([sys.executable, '-B', '-m', module, *map(str, args)],
                   cwd=ROOT, env=env, check=True)


def read(path: Path):
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths(name: str):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name):
        raise ValueError('name must be 1–64 letters, digits, underscores or hyphens')
    return tuple(BASE / f'{stage}_{name}' for stage in
                 ('protocol', 'run', 'audit', 'trace_audit', 'report'))


def prepare(name: str) -> None:
    protocol, *_ = paths(name)
    call('e6_validation.runtime_v4', 'freeze', '--out', protocol,
         '--cases', *CASES, '--planner', 'deterministic_task_planner', '--split', 'development',
         '--arms', *ARMS, '--conditions', *CONDITIONS, '--modes', 'pair',
         '--persistence', 'persistent', '--seed', '260625')


def run(name: str) -> None:
    protocol, run_dir, *_ = paths(name)
    call('e6_validation.runtime_v4', 'run', '--protocol', protocol / 'protocol.json',
         '--out', run_dir, '--limit', '24')
    summary = read(ROOT / run_dir / 'summary.json')
    if summary['status'] != 'COMPLETE' or summary['completed'] != summary['expected']:
        raise RuntimeError('Native run incomplete or failed; see run/summary.json and attempts')


def report(name: str) -> None:
    protocol, run_dir, audit, trace, report_dir = paths(name)
    target = ROOT / report_dir
    if target.exists():
        raise FileExistsError('report directory already exists')
    summary = read(ROOT / run_dir / 'summary.json')
    if summary['status'] != 'COMPLETE' or summary['completed'] != summary['expected']:
        raise RuntimeError('Refusing full report for incomplete run')
    if not (ROOT / audit).exists():
        call('e6_validation.runtime_audit_v4', '--run', run_dir, '--out', audit)
    previous = read(ROOT / audit / 'audit.json')
    if previous.get('status') != 'PASS_NATIVE_CUSTOM_PIPELINE' or previous.get('source_run') != str(run_dir):
        raise RuntimeError('Prior audit does not match this run')
    # Re-run the independent native audit in memory even when its output already
    # exists; source hashes and checkpoint hashes must remain valid.
    from e6_validation.runtime_audit_v4 import audit as verify
    from e6_validation.runtime_v4 import check_protocol
    from e5_validation.common import file_sha
    for path, expected in read(ROOT / run_dir / 'artifact_sha256.json').items():
        if file_sha(ROOT / path) != expected:
            raise RuntimeError('Changed run artifact: ' + path)
    checked = check_protocol(ROOT / protocol / 'protocol.json')
    if digest(ROOT / protocol / 'protocol.json') != read(ROOT / run_dir / 'run_manifest.json')['protocol_sha256']:
        raise RuntimeError('Changed protocol')
    verify(ROOT / run_dir, checked)
    if not (ROOT / trace).exists():
        call('e6_validation.trace_audit', '--track', run_dir, audit / 'audit.json', '--out', trace)
    trace_audit = read(ROOT / trace / 'audit.json')
    if trace_audit.get('status') != 'PASS_SUPPLEMENTAL_TRACE_AUDIT':
        raise RuntimeError('Supplemental trace audit failed')
    expected_run = str(run_dir)
    if not any(x['run'] == expected_run and x['audited'] == summary['expected']
               for x in trace_audit['tracks']):
        raise RuntimeError('Supplemental audit is for a different run')

    from e6_validation.runtime_v4 import load_rows
    from e6_validation.evidence_checks import verify_episode
    episodes = load_rows(ROOT / run_dir)
    for episode in episodes:
        verify_episode(episode)
    pairs = {}
    for row in episodes:
        key = (row['case_id'], row['condition'])
        pairs.setdefault(key, {})[row['arm']] = row['plan']['actions']
    comparisons = []
    for (case, condition), by_arm in sorted(pairs.items()):
        comparisons.append({'case_id': case, 'condition': condition, 'arm_count': len(by_arm),
                            'all_arms_present': set(by_arm) == set(ARMS),
                            'actions_match': all(x == next(iter(by_arm.values())) for x in by_arm.values())})
    groups = []
    for group in summary['groups']:
        row = {k: group[k] for k in ('family', 'condition', 'arm', 'completed_episodes',
                                     'protected_queries', 'producer_publications', 'median_pipeline_ms')}
        for metric in ('UAR_candidate', 'attack_execution_ASR', 'safe_task_success',
                       'false_BLOCK_benign', 'false_DEFER_benign', 'planner_fact_propagation',
                       'monitor_fact_propagation', 'trusted_critical_evidence_coverage'):
            for field, value in group[metric].items():
                row[f'{metric}_{field}'] = value
        groups.append(row)
    target.mkdir(parents=True)
    with (target / 'metrics.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(groups[0]))
        writer.writeheader()
        writer.writerows(groups)
    output = dict(status='AUDITED_DEVELOPMENT_PROTOTYPE', intended_assignments=checked['expected'],
                  completed=summary['completed'], split='observed_development',
                  planner_mode='deterministic_task_planner', native_unity=True, online_model_calls=0,
                  groups=groups, action_match_by_case_condition=comparisons,
                  source_protocol=str(protocol / 'protocol.json'), source_run=str(run_dir),
                  source_audit=str(audit / 'audit.json'), source_trace_audit=str(trace / 'audit.json'),
                  limitations=['Not a new heldout or population estimate',
                               'Same Unity protected query is not an independent physical sensor',
                               'Relation drift is induced by the evaluator, not attacker capability',
                               'Different conditions may use different plans; matching is checked only within condition',
                               'No external Guard adapter or online LLM in this prototype'])
    (target / 'summary.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print('BENCHMARK_V0_REPORT', target / 'summary.json', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'report', 'all'))
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    if args.command in ('prepare', 'all'):
        prepare(args.name)
    if args.command in ('run', 'all'):
        run(args.name)
    if args.command in ('report', 'all'):
        report(args.name)


if __name__ == '__main__':
    # Allow module imports when launched as `python scripts/benchmark_v0.py`.
    sys.path.insert(0, str(ROOT))
    main()
