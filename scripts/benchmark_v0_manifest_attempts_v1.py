"""Export all planned candidate assignments, including failed and unknown ones."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha
from benchmark_v0_manifest_runner_v1 import verify_protocol
from benchmark_v0_attempts_v2 import validate,summarize


def load(p): return json.loads(p.read_text())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',required=True); ap.add_argument('--audit',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args(); run,audit,out=map(checked_path,(a.run,a.audit,a.out))
    p=verify_protocol(run/'protocol.json'); j=load(run/'journal.json'); report=load(audit/'audit.json')
    if (report['status']!='PASS_MANIFEST_SUITE_COMPOSITION_AUDIT' or
        report['source_run']!=str(run.relative_to(ROOT)) or report['source_protocol_sha256']!=sha(run/'protocol.json') or
        report['source_journal_sha256']!=sha(run/'journal.json') or report['source_summary_sha256']!=sha(run/'summary.json')):
        raise ValueError('suite audit provenance mismatch')
    rows=[]
    for case in j['cases']:
        for e in case['episodes']:
            row=dict(schema='embodied.evidence_benchmark.attempt.v2',assignment_id=e['assignment_id'],
                     case_id=e['case_id'],scene=e['scene'],condition=e['condition'],guard=e['guard'],
                     status='UNKNOWN',audit_status='NOT_AUDITED',reason='no trustworthy terminal record',
                     truth_safe=None,decision=None,candidate_submitted=None,execution_violation=None,
                     safe_candidate_executed=None,protected_query_count=None,source_episode_sha256=None)
            if e['status'] in ('COMPLETED_RECORDED','INCOMPLETE_RECORDED'):
                path=run/('run_'+case['case_id'])/'private'/f"{e['index']:02d}_episode.json"
                if sha(path)!=e['source_episode_sha256']: raise ValueError('episode hash differs')
                src=load(path); row['source_episode_sha256']=sha(path)
                if e['status']=='COMPLETED_RECORDED':
                    receipt=src['executor_receipt']
                    row.update(status='COMPLETED',audit_status='PASS' if e['audit_status']=='PASS' else 'NOT_AUDITED',reason=None,
                               truth_safe=src['true_contract_satisfied'],decision=src['decision'],candidate_submitted=receipt is not None,
                               execution_violation=src['execution_violation'],safe_candidate_executed=src['safe_candidate_executed'],
                               protected_query_count=int(src['protected_query'] is not None))
                else: row.update(status='INCOMPLETE',reason='legacy runner reports FAILED_OR_INCOMPLETE; inspect case log')
            elif e['status']=='TIMEOUT_OBSERVED': row.update(status='TIMEOUT',reason=e['reason'])
            elif e['status']=='PLANNED' and case['status']=='PLANNED': row.update(status='NOT_STARTED',reason='case not launched')
            elif e['status']!='UNKNOWN': raise ValueError('unexpected episode status')
            validate(row); rows.append(row)
    if len(rows)!=p['planned_episodes'] or len({r['assignment_id'] for r in rows})!=len(rows):
        raise ValueError('planned assignment coverage')
    result=summarize(rows)
    result.update(schema='embodied.evidence_benchmark.manifest_attempt_summary.v1',
                  source_protocol_sha256=sha(run/'protocol.json'),source_journal_sha256=sha(run/'journal.json'),
                  source_suite_audit_sha256=sha(audit/'audit.json'),exporter_sha256=sha(Path(__file__).resolve()),
                  limitations=p['limitations']+['Only audited completed episodes enter safety metrics',
                    'Incomplete/unknown are not safe or unsuccessful attacks',
                    'Planned 48 episodes are not 48 independent scenes'])
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'attempts.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for file in out.iterdir(): os.chmod(file,0o600)
    print('MANIFEST_ATTEMPTS',len(rows),result['status_counts'],'AUDITED',result['audited_completed'])

if __name__=='__main__': main()
