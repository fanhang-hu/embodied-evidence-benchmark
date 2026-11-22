"""Verify suite composition and all per-case audit and artifact references."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, verify_protocol, sha


def load(path):
    return json.loads(path.read_text())


def must(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True); p.add_argument('--out', required=True)
    args = p.parse_args()
    run, out = checked_path(args.run), checked_path(args.out)
    must(not out.exists(), 'Audit output already exists')
    protocol = verify_protocol(run / 'protocol.json')
    status, summary, manifest = (load(run / name) for name in ('status.json', 'summary.json', 'suite_artifact_sha256.json'))
    must(status['status'] == 'COMPLETE' and summary['status'] == 'COMPLETE_AUDITED_DEVELOPMENT_SUITE', 'Incomplete suite')
    must(status['expected'] == status['completed'] == summary['expected'] == summary['completed'] == protocol['expected_episodes'], 'Episode count')
    must(status['source_protocol_sha256'] == summary['source_protocol_sha256'] == sha(run / 'protocol.json'), 'Frozen protocol hash')
    expected_manifest = {str(f.relative_to(run)) for f in run.rglob('*') if f.is_file()
                         and f.name not in ('artifact_sha256.json', 'guard_access_canary.txt', 'suite_artifact_sha256.json')}
    must(set(manifest) == expected_manifest, 'Suite artifact set differs')
    for name, expected in manifest.items():
        must(sha(run / name) == expected, 'Artifact hash: ' + name)
    must([x['case_id'] for x in status['cases']] == [x['case_id'] for x in protocol['cases']], 'Case order')
    groups = []
    for spec, entry in zip(protocol['cases'], status['cases']):
        case_id = spec['case_id']
        case_run, case_audit = run / ('run_' + case_id), run / ('audit_' + case_id)
        must(entry['status'] == 'AUDITED' and entry['scene'] == spec['scene'], 'Case status')
        must(entry['run'] == str(case_run.relative_to(ROOT)) and entry['audit'] == str(case_audit.relative_to(ROOT)), 'Case paths')
        must(sha(case_audit / 'audit.json') == entry['audit_sha256'] and
             sha(case_run / 'artifact_sha256.json') == entry['manifest_sha256'], 'Case artifact references')
        audit, case_protocol, case_summary = (load(p) for p in (case_audit / 'audit.json', case_run / 'protocol.json', case_run / 'summary.json'))
        must(audit['status'] == 'PASS_ISOLATED_GUARD_NATIVE_AUDIT' and audit['audited'] == 12, 'Case audit')
        must(audit['source_manifest_sha256'] == entry['manifest_sha256'], 'Audit bound to case manifest')
        must(case_protocol['case_id'] == case_id and case_protocol['scene'] == spec['scene'] and
             case_protocol['contract'] == protocol['contract'], 'Case protocol')
        must(len(case_summary['groups']) == 12, 'Case group count')
        groups.extend(dict(case_id=case_id, scene=spec['scene'], **g) for g in case_summary['groups'])
    must(groups == summary['groups'], 'Suite group aggregation')
    out.mkdir(parents=True, mode=0o700)
    os.chmod(out, 0o700)
    result = dict(status='PASS_SUITE_COMPOSITION_AUDIT', episodes=status['completed'],
                  cases=len(status['cases']), source_suite=str(run.relative_to(ROOT)),
                  suite_manifest_sha256=sha(run / 'suite_artifact_sha256.json'),
                  source_sha256=sha(Path(__file__).resolve()),
                  limitations=['Checks composition and hashes; does not rerun Unity or per-case audits',
                               'Per-case independent audits have their own recorded limitations'])
    path = out / 'audit.json'; path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n'); os.chmod(path, 0o600)
    print('PASS_SUITE_COMPOSITION_AUDIT', result['episodes'], flush=True)


if __name__ == '__main__':
    main()
