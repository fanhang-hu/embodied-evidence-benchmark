"""Frozen, case-configurable development suite around the audited V0 pilot.

Each selected relation case gets the pilot's fixed 3 x 4 matrix and a separate
independent audit. This is a development suite, not a held-out benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from e5_validation.common import CATALOGUE, read_jsonl
from benchmark_v0_guard_sandbox import FILES

BASE = (ROOT / 'results/benchmark_v0').resolve()
SOURCES = ['scripts/benchmark_v0_suite_v1.py', 'scripts/benchmark_v0_external_native.py',
           'scripts/benchmark_v0_external_native_audit.py', 'scripts/benchmark_v0_guard_sandbox.py',
           str(CATALOGUE), 'e4_validation/protocol.py', 'e4_validation/simulator.py',
           'e5_validation/common.py', 'e6_validation/producer_experiment.py',
           'e6_validation/producer_boundary.py', 'e6_validation/producer_worker.py'] + [x for x, _ in FILES]
ARMS = ['public_reference', 'external_bound', 'fail_closed', 'critical_only_fresh']
CONDITIONS = ['benign_safe', 'clean_unsafe', 'producer_attack']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    os.chmod(path, 0o600)


def checked_path(value):
    p = Path(value)
    p = (ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    if not p.is_relative_to(BASE) or p == BASE:
        raise ValueError('Output/protocol must be below results/benchmark_v0')
    return p


def hashes():
    return {p: sha(ROOT / p) for p in dict.fromkeys(SOURCES)}


def freeze(args):
    if len(set(args.cases)) != len(args.cases):
        raise ValueError('Duplicate case IDs')
    catalogue = {c['case_id']: c for c in read_jsonl(ROOT / CATALOGUE)}
    cases = []
    for case_id in args.cases:
        if case_id not in catalogue or not case_id.startswith('relation_'):
            raise ValueError('Unknown or unsupported relation case: ' + case_id)
        c = catalogue[case_id]
        cases.append({k: c[k] for k in ('case_id', 'scene', 'pan_id', 'burner_id', 'knob_id')})
    out = checked_path(args.out)
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(out, 0o700)
    protocol = dict(schema='benchmark.v0.case_suite.v1', split='observed_development',
                    planner='fixed_candidate_no_planner', contract='any_cookware_v0',
                    cases=cases, conditions=CONDITIONS, guards=ARMS,
                    expected_episodes=len(cases)*len(CONDITIONS)*len(ARMS),
                    pilot_seed=260626, source_sha256=hashes(),
                    limitations=['Fixed suite of four known adapters; not an arbitrary plugin API',
                                 'Cases previously observed during development; not held-out',
                                 'One fixed action per episode; no online planner or full task success',
                                 'Any-cookware precondition is not a complete safety policy',
                                 'Independent trusted Unity query is an oracle-like protected channel'])
    write(out / 'protocol.json', protocol)
    print('FROZEN', out / 'protocol.json', flush=True)


def verify_protocol(p):
    protocol = json.loads(p.read_text())
    if protocol.get('schema') != 'benchmark.v0.case_suite.v1' or protocol.get('source_sha256') != hashes():
        raise ValueError('Protocol schema or source hashes differ')
    if protocol['conditions'] != CONDITIONS or protocol['guards'] != ARMS:
        raise ValueError('Unsupported suite')
    catalog = {c['case_id']: c for c in read_jsonl(ROOT / CATALOGUE)}
    cases = protocol['cases']
    if not cases or len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Empty/duplicate cases')
    for c in cases:
        if not c['case_id'].startswith('relation_') or any(c[k] != catalog[c['case_id']][k] for k in c):
            raise ValueError('Case changed')
    if protocol['expected_episodes'] != len(cases)*len(CONDITIONS)*len(ARMS):
        raise ValueError('Expected episode count changed')
    return protocol


def child(args):
    # Run the unmodified, hash-frozen pilot and its independent audit.
    import benchmark_v0_external_native as pilot
    import benchmark_v0_external_native_audit as audit
    pilot.CASE_ID = args.case
    pilot.OUT = checked_path(args.run)
    pilot.main()
    audit.RUN = pilot.OUT
    audit.OUT = checked_path(args.audit)
    audit.main()


def run(args):
    protocol_path = checked_path(args.protocol)
    protocol = verify_protocol(protocol_path)
    out = checked_path(args.out)
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(out, 0o700)
    write(out / 'protocol.json', protocol)
    state = dict(status='STARTED', expected=protocol['expected_episodes'], completed=0,
                 source_protocol_sha256=sha(protocol_path), cases=[])
    write(out / 'status.json', state)
    groups = []
    try:
        for c in protocol['cases']:
            case_id = c['case_id']
            run_path, audit_path = out / ('run_' + case_id), out / ('audit_' + case_id)
            entry = dict(case_id=case_id, scene=c['scene'], status='STARTED')
            state['cases'].append(entry)
            write(out / 'status.json', state)
            cmd = [sys.executable, '-B', str(Path(__file__).resolve()), 'child', '--case', case_id,
                   '--run', str(run_path), '--audit', str(audit_path)]
            result = subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                                                       'LIBGL_ALWAYS_SOFTWARE': '1'}, check=False)
            if result.returncode:
                entry.update(status='FAILED_OR_INCOMPLETE', returncode=result.returncode)
                raise RuntimeError('Case failed: ' + case_id)
            summary = json.loads((run_path / 'summary.json').read_text())
            audit = json.loads((audit_path / 'audit.json').read_text())
            if summary['completed'] != 12 or audit['status'] != 'PASS_ISOLATED_GUARD_NATIVE_AUDIT' or audit['audited'] != 12:
                raise ValueError('Run or audit incomplete: ' + case_id)
            for row in summary['groups']:
                groups.append(dict(case_id=case_id, scene=c['scene'], **row))
            entry.update(status='AUDITED', run=str(run_path.relative_to(ROOT)),
                         audit=str(audit_path.relative_to(ROOT)), audit_sha256=sha(audit_path / 'audit.json'),
                         manifest_sha256=sha(run_path / 'artifact_sha256.json'))
            state['completed'] += 12
            write(out / 'status.json', state)
        if state['completed'] != state['expected']:
            raise ValueError('Incomplete suite')
        summary = dict(status='COMPLETE_AUDITED_DEVELOPMENT_SUITE', completed=state['completed'],
                       expected=state['expected'], scene_count=len({c['scene'] for c in protocol['cases']}),
                       source_protocol_sha256=state['source_protocol_sha256'], groups=groups,
                       limitations=protocol['limitations'], new_online_model_calls=0)
        write(out / 'summary.json', summary)
        state['status'] = 'COMPLETE'
    except Exception as exc:
        state.update(status='FAILED_OR_INCOMPLETE', error=repr(exc), traceback=traceback.format_exc())
        raise
    finally:
        write(out / 'status.json', state)
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
                if p.is_file() and p.name not in ('artifact_sha256.json', 'guard_access_canary.txt')}
    write(out / 'suite_artifact_sha256.json', manifest)
    print('SUITE_COMPLETE', out / 'summary.json', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze'); p.add_argument('--out', required=True); p.add_argument('--cases', nargs='+', required=True); p.set_defaults(func=freeze)
    p = sub.add_parser('run'); p.add_argument('--protocol', required=True); p.add_argument('--out', required=True); p.set_defaults(func=run)
    p = sub.add_parser('child'); p.add_argument('--case', required=True); p.add_argument('--run', required=True); p.add_argument('--audit', required=True); p.set_defaults(func=child)
    args = parser.parse_args(); args.func(args)


if __name__ == '__main__':
    main()
