"""Independently compare unified episode results with the two source exports."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha


def load(p): return json.loads(p.read_text())
def must(x,message):
    if not x: raise ValueError(message)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',required=True); ap.add_argument('--relation-export',required=True)
    ap.add_argument('--attribute-export',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); run,rel,attr,out=map(checked_path,(args.run,args.relation_export,args.attribute_export,args.out))
    summary=load(run/'summary.json'); card=load(ROOT/'benchmark_v0/spec/unified_card.v1.json')
    schema=load(ROOT/'benchmark_v0/spec/unified_episode.schema.v1.json')
    rows=[json.loads(x) for x in (run/'episodes.jsonl').read_text().splitlines() if x.strip()]
    cases=[json.loads(x) for x in (run/'cases.jsonl').read_text().splitlines() if x.strip()]
    must(summary['schema']=='embodied.evidence_benchmark.unified_summary.v1' and summary['planned']==len(rows) and
         summary['cases']==len(cases) and summary['method_matrix']==card['method_matrix'],'summary/card')
    for path,expected in summary['source_sha256'].items(): must(sha(ROOT/path)==expected,'source changed: '+path)
    must(summary['source_sha256'].get(str((rel/'attempts.jsonl').relative_to(ROOT)))==sha(rel/'attempts.jsonl') and
         summary['source_sha256'].get(str((attr/'episodes.jsonl').relative_to(ROOT)))==sha(attr/'episodes.jsonl'),'export binding')
    must(len({r['episode_id'] for r in rows})==len(rows) and len({(c['contract'],c['case_id']) for c in cases})==len(cases),'duplicates')
    case_set={(c['contract'],c['case_id'],c['scene'],c['family']) for c in cases}
    relation_rows=[json.loads(x) for x in (rel/'attempts.jsonl').read_text().splitlines() if x.strip()]
    attribute_rows=[json.loads(x) for x in (attr/'episodes.jsonl').read_text().splitlines() if x.strip()]
    source_rows={}
    for r in relation_rows:
        source_rows['any_cookware_v0:'+r['assignment_id']]=r
    for r in attribute_rows:
        source_rows['target_knob_off_v0:'+r['episode_id']]=r
    must(len(source_rows)==len(rows) and set(source_rows)=={r['episode_id'] for r in rows},'source episode coverage')
    for r in rows:
        origin=source_rows[r['episode_id']]
        must(all(r[k]==origin[k] for k in ('case_id','scene','condition','audit_status','truth_safe','decision','candidate_submitted','execution_violation','safe_candidate_executed','protected_query_count','source_episode_sha256')) and r['method']==origin['guard'], 'source episode mismatch')
        expected_status='INCOMPLETE' if origin['status']=='FAILED_OR_INCOMPLETE' else origin['status']
        must(r['status']==expected_status,'source status mismatch')
        must(set(r)==set(schema['required']) and (r['contract'],r['case_id'],r['scene'],r['family']) in case_set,'record fields/case')
        m=card['method_matrix'][r['contract']].get(r['method'])
        must(m and m['status']=='MEASURED' and r['mechanism_class']==m['mechanism_class'] and r['evidence_capability']==m['evidence'], 'method capability')
        if r['status']=='COMPLETED':
            must(type(r['truth_safe']) is bool and r['candidate_submitted']==(r['decision']=='ALLOW') and
                 type(r['protected_query_count']) is int and type(r['producer_publication_count']) is int,'completed semantics')
        else:
            must(r['audit_status']!='PASS' and all(r[k] is None for k in ('truth_safe','decision','candidate_submitted',
                 'execution_violation','safe_candidate_executed','protected_query_count','producer_publication_count')),'incomplete semantics')
    must(summary['audited_completed']==sum(r['status']=='COMPLETED' and r['audit_status']=='PASS' for r in rows),'audited count')
    sources={'any_cookware_v0':load(rel/'summary.json')['groups'], 'target_knob_off_v0':load(attr/'summary.json')['groups']}
    metric_keys=('unsafe_authorization_rate','execution_violation_rate','safe_candidate_execution_rate','false_defer_rate','false_block_rate')
    expected_groups=sum(3*sum(m['status']=='MEASURED' for m in methods.values()) for methods in card['method_matrix'].values())
    must(len(summary['groups'])==expected_groups and len({(g['contract'],g['condition'],g['method']) for g in summary['groups']})==expected_groups,'group count/uniqueness')
    for g in summary['groups']:
        candidates=[x for x in sources[g['contract']] if x['condition']==g['condition'] and x['guard']==g['method']]
        must(len(candidates)==1,'missing source group'); origin=candidates[0]
        must(g['planned']==origin['planned'] and g['audited_completed']==origin.get('audited_completed',origin.get('completed')),'group counts')
        for key in metric_keys: must(g[key]==origin[key],f'source metric differs: {g["contract"]}/{g["method"]}/{key}')
        chosen=[r for r in rows if r['contract']==g['contract'] and r['condition']==g['condition'] and r['method']==g['method'] and r['status']=='COMPLETED' and r['audit_status']=='PASS']
        must(len(chosen)==g['audited_completed'] and sum(r['protected_query_count'] for r in chosen)==g['protected_query_count'] and
             sum(r['producer_publication_count'] for r in chosen)==g['producer_publication_count'],'query counts')
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    result=dict(status='PASS_UNIFIED_EXPORT_AUDIT',episodes=len(rows),cases=len(cases),groups=len(summary['groups']),
                audited_completed=summary['audited_completed'],source_summary_sha256=sha(run/'summary.json'),
                source_episodes_sha256=sha(run/'episodes.jsonl'),source_cases_sha256=sha(run/'cases.jsonl'),
                auditor_sha256=sha(Path(__file__).resolve()),
                limitations=['Checks derived files and source metrics; does not rerun Unity or Guard',
                             'Relies on existing source audits and their limitations','Not a formal JSON Schema implementation'])
    p=out/'audit.json'; p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); os.chmod(p,0o600)
    print(result['status'],result['episodes'],'episodes',result['groups'],'groups')

if __name__=='__main__': main()
