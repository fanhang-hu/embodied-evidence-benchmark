"""Check native unified records against source rows and source group counts."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha


def load(p): return json.loads(p.read_text())
def must(x,m):
    if not x: raise ValueError(m)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('run','relation-run','attribute-run','out'): ap.add_argument('--'+key,required=True)
    a=ap.parse_args(); run,rr,ar,out=map(checked_path,(a.run,a.relation_run,a.attribute_run,a.out))
    s=load(run/'summary.json'); card=load(ROOT/'benchmark_v0/spec/unified_card.v2.json')
    for path,h in s['source_sha256'].items(): must(sha(ROOT/path)==h,'source changed '+path)
    for f in (rr/'protocol.json',rr/'artifact_sha256.json',ar/'protocol.json',ar/'artifact_sha256.json'):
        must(s['source_sha256'].get(str(f.relative_to(ROOT)))==sha(f),'run binding')
    rows=[json.loads(x) for x in (run/'episodes.jsonl').read_text().splitlines() if x.strip()]
    cases=[json.loads(x) for x in (run/'cases.jsonl').read_text().splitlines() if x.strip()]
    must(s['planned']==len(rows) and s['cases']==len(cases) and len({r['episode_id'] for r in rows})==len(rows),'coverage')
    must(s['method_matrix']==card['method_matrix'],'capabilities')
    for r in rows:
        root=rr if r['contract']=='any_cookware_v0' else ar
        index=int(r['episode_id'].rsplit(':',1)[-1]); path=root/'private'/f'{index:02d}_episode.json'; src=load(path)
        must(sha(path)==r['source_episode_sha256'] and src['case_id']==r['case_id'] and src['condition']==r['condition'] and src['arm']==r['method'],'record source')
        if src['status']=='COMPLETED':
            must(r['status']=='COMPLETED' and r['audit_status']=='PASS' and
                 r['truth_safe']==src['true_contract_satisfied'] and r['decision']==src['decision'] and
                 r['candidate_submitted']==(src['executor_receipt'] is not None) and
                 r['execution_violation']==src['execution_violation'] and r['safe_candidate_executed']==src['safe_candidate_executed'] and
                 r['protected_query_count']==int(src['protected_query'] is not None) and
                 r['producer_publication_count']==len(src['producer_publications']),'outcome mismatch')
        else: must(r['status']=='INCOMPLETE' and r['audit_status']=='NOT_AUDITED','failed record')
    must(s['audited_completed']==sum(r['status']=='COMPLETED' and r['audit_status']=='PASS' for r in rows),'completed count')
    expected_groups={(contract,cond,method) for contract,methods in card['method_matrix'].items()
                     for cond in ('benign_safe','clean_unsafe','producer_attack') for method,info in methods.items() if info['status']=='MEASURED'}
    must({(g['contract'],g['condition'],g['method']) for g in s['groups']}==expected_groups and len(s['groups'])==len(expected_groups),'group coverage')
    for g in s['groups']:
        source=load((rr if g['contract']=='any_cookware_v0' else ar)/'summary.json')
        original=[x for x in source['groups'] if x['condition']==g['condition'] and x['arm']==g['method']]
        must(len(original)==1,'missing source group'); original=original[0]
        must((g['planned'],g['audited_completed'])==(original['planned'],original['completed']),'group sizes')
        for metric,num,den in (('unsafe_authorization_rate','unsafe_allowed','unsafe_candidates'),
                               ('execution_violation_rate','actual_violations','unsafe_candidates'),
                               ('safe_candidate_execution_rate','safe_candidate_executed','safe_candidates'),
                               ('false_defer_rate','safe_deferred','safe_candidates')):
            r=g[metric]; n,d=original[num],original[den]
            must(r==dict(numerator=n,denominator=d,value=n/d if d else None),'group metric '+metric)
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    result=dict(status='PASS_NATIVE_UNIFIED_AUDIT',episodes=len(rows),cases=len(cases),groups=len(s['groups']),
                source_summary_sha256=sha(run/'summary.json'),source_episodes_sha256=sha(run/'episodes.jsonl'),
                source_cases_sha256=sha(run/'cases.jsonl'),auditor_sha256=sha(Path(__file__).resolve()),
                limitations=['Does not rerun Unity or Guard','Relies on source audits and their scope',
                             'No claim of independent heldout cases or pooled rates'])
    path=out/'audit.json'; path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); os.chmod(path,0o600)
    print(result['status'],result['episodes'],'episodes',result['groups'],'groups')

if __name__=='__main__': main()
