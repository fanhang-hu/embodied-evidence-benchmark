"""Combine audited legacy records with observed episode timeout journal."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha
from benchmark_v0_attempts_v2 import normalize, summarize, validate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--protocol', required=True); ap.add_argument('--run', required=True); ap.add_argument('--out', required=True)
    args = ap.parse_args(); protocol, run, out = map(checked_path, (args.protocol, args.run, args.out))
    journal_path = run / 'journal.json'; journal = json.loads(journal_path.read_text())
    if journal.get('schema') != 'embodied.evidence_benchmark.episode_observation.v1' or journal.get('source_protocol_sha256') != sha(protocol):
        raise ValueError('journal protocol/schema mismatch')
    if 'finished_wall_time_ns' not in journal or journal['status'] == 'STARTED':
        raise ValueError('journal has no terminal supervisor status')
    rows = normalize(protocol, run)
    entries = {r['assignment_id']: r for c in journal['cases'] for r in c['episodes']}
    if len(entries) != len(rows) or set(entries) != {r['assignment_id'] for r in rows}:
        raise ValueError('journal assignment coverage')
    case_status = {c['case_id']: c['status'] for c in journal['cases']}
    for row in rows:
        entry = entries[row['assignment_id']]
        if any(entry[k] != row[k] for k in ('case_id', 'scene', 'condition', 'guard')):
            raise ValueError('journal assignment mismatch')
        if entry['status'] == 'COMPLETED_RECORDED':
            if row['status'] != 'COMPLETED' or entry['source_episode_sha256'] != row['source_episode_sha256']:
                raise ValueError('completed episode differs from journal')
            if (entry['audit_status'] == 'PASS') != (row['audit_status'] == 'PASS'):
                raise ValueError('journal audit differs from case audit')
        elif entry['status'] == 'INCOMPLETE_RECORDED':
            if row['status'] != 'INCOMPLETE' or entry['source_episode_sha256'] != row['source_episode_sha256']:
                raise ValueError('incomplete episode differs from journal')
        elif entry['status'] == 'TIMEOUT_OBSERVED':
            if row['status'] != 'UNKNOWN' or case_status[row['case_id']] != 'EPISODE_TIMEOUT':
                raise ValueError('timeout observation inconsistent')
            row.update(status='TIMEOUT', reason=entry['reason'])
        elif entry['status'] == 'PLANNED':
            if row['status'] != 'UNKNOWN' or case_status[row['case_id']] != 'PLANNED':
                raise ValueError('not-started observation inconsistent')
            row.update(status='NOT_STARTED', reason='supervisor never launched this case')
        elif entry['status'] != 'UNKNOWN':
            raise ValueError('unrecognized terminal journal entry')
        validate(row)
    summary = summarize(rows)
    summary.update(schema='embodied.evidence_benchmark.attempt_summary.v2',
                   source_protocol_sha256=sha(protocol), source_journal_sha256=sha(journal_path),
                   source_exporter_sha256=sha(Path(__file__).resolve()),
                   limitations=['Observed episode start is polling-based, not exact',
                                'Timeout label requires final legacy progress still pointing to the observed episode',
                                'Audit status depends on existing case audit and artifact manifest',
                                'Only audited completed episodes enter safety metric denominators',
                                'Failures/unsupported lack finer legacy-driver classification'])
    out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    (out / 'attempts.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    for p in out.iterdir(): os.chmod(p, 0o600)
    print('JOURNAL_EXPORT', len(rows), 'AUDITED_COMPLETED', summary['audited_completed'], 'STATUSES', summary['status_counts'])

if __name__ == '__main__': main()
