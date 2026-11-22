"""Check candidate suite composition against frozen protocol and case audit records."""
import argparse
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import ARMS, CONDITIONS, checked_path, sha
from benchmark_v0_candidate_evaluation_v1 import protocol_check
from benchmark_v0_attempts_v2 import audited_case


def must(test, message):
    if not test: raise ValueError(message)


def load(p): return json.loads(p.read_text())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); run,out=checked_path(args.run),checked_path(args.out)
    protocol=protocol_check(run/'protocol.json'); journal=load(run/'journal.json'); summary=load(run/'summary.json')
    must(journal['status'] in ('COMPLETE','COMPLETE_WITH_FAILURES','INTERRUPTED','FAILED'), 'nonterminal journal')
    must(summary['status']==journal['status'] and summary['journal_sha256']==sha(run/'journal.json') and
         summary['source_protocol_sha256']==journal['source_protocol_sha256']==sha(run/'protocol.json'), 'provenance')
    must(journal['planned_episodes']==summary['planned_episodes']==protocol['planned_episodes'], 'planned count')
    must([c['case_id'] for c in journal['cases']]==[c['case_id'] for c in protocol['cases']], 'case order')
    audited=[]
    for case,case_protocol in zip(journal['cases'],protocol['cases']):
        cid=case['case_id']; must(case['scene']==case_protocol['scene'], 'scene')
        expected=[dict(condition=c,guard=a) for c in CONDITIONS for a in ARMS]; random.Random(protocol['seed']).shuffle(expected)
        must(len(case['episodes'])==len(expected)==12, 'assignment count')
        for i,(r,a) in enumerate(zip(case['episodes'],expected)):
            must(r['case_id']==cid and r['index']==i and r['assignment_id']==f'{cid}:{i:02d}' and
                 r['condition']==a['condition'] and r['guard']==a['guard'], 'assignment mismatch')
            if r['status'] in ('COMPLETED_RECORDED','INCOMPLETE_RECORDED'):
                path=run/('run_'+cid)/'private'/f'{i:02d}_episode.json'
                must(sha(path)==r['source_episode_sha256'], 'episode hash')
        if case['status']=='AUDITED':
            must(audited_case(run,cid), 'per-case audit or manifest')
            must(sha(run/('audit_'+cid)/'audit.json')==case['audit_sha256'] and
                 sha(run/('run_'+cid)/'artifact_sha256.json')==case['manifest_sha256'], 'audit hash')
            cp=load(run/('run_'+cid)/'protocol.json')
            must(cp['case_id']==cid and cp['scene']==case['scene'] and cp['contract']==protocol['contract'], 'case protocol')
            must(all(r['status']=='COMPLETED_RECORDED' and r['audit_status']=='PASS' for r in case['episodes']), 'episode audit status')
            audited.append(case)
        else:
            must(all(r['audit_status']!='PASS' for r in case['episodes']), 'failed case silently audited')
    must(summary['audited_cases']==len(audited) and summary['planned_cases']==len(protocol['cases']), 'summary count')
    must(summary['cases']==[dict(case_id=c['case_id'],scene=c['scene'],status=c['status']) for c in journal['cases']], 'case summary')
    rebuilt=[]
    for condition in CONDITIONS:
        for arm in ARMS:
            collected=[]
            for case in audited:
                groups=load(run/('run_'+case['case_id'])/'summary.json')['groups']
                records=[r for r in groups if r['condition']==condition and r['arm']==arm]
                must(len(records)==1, 'case group')
                collected.extend(records)
            sums={key:sum(r[key] for r in collected) for key in ('unsafe_candidates','unsafe_allowed','actual_violations',
                  'safe_candidates','safe_candidate_executed','safe_deferred','protected_queries')}
            rebuilt.append(dict(condition=condition,guard=arm,planned=len(journal['cases']),audited_completed=len(collected),**sums))
    must(summary['groups']==rebuilt, 'aggregated metrics')
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    report=dict(status='PASS_CANDIDATE_SUITE_COMPOSITION_AUDIT',source_run=str(run.relative_to(ROOT)),
                source_protocol_sha256=sha(run/'protocol.json'),source_journal_sha256=sha(run/'journal.json'),
                source_summary_sha256=sha(run/'summary.json'),auditor_sha256=sha(Path(__file__).resolve()),
                planned_cases=len(protocol['cases']),audited_cases=len(audited),
                limitations=['Checks case audit outputs and artifacts; does not rerun Unity or Guard',
                             'Case auditor and pilot share explicitly injected frozen case metadata',
                             'Historical scene independence remains unverified',
                             'Failures remain failures; audits of completed cases do not validate incomplete cases'])
    p=out/'audit.json'; p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); os.chmod(p,0o600)
    print(report['status'],report['audited_cases'],'/',report['planned_cases'])

if __name__=='__main__': main()
