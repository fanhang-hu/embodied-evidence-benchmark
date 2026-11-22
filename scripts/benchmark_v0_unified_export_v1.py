"""Build a provenance-checked unified result bundle from two audited development tracks."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha
from benchmark_v0_manifest_runner_v1 import verify_protocol as verify_relation
from benchmark_v0_attribute_native_v1 import verify as verify_attribute
from benchmark_v0_attempts_v2 import audited_case

CARD=ROOT/'benchmark_v0/spec/unified_card.v1.json'
SCHEMA=ROOT/'benchmark_v0/spec/unified_episode.schema.v1.json'
STATES=('COMPLETED','FAILED','INCOMPLETE','TIMEOUT','UNSUPPORTED','NOT_STARTED','UNKNOWN')
OUTCOMES=('truth_safe','decision','candidate_submitted','execution_violation','safe_candidate_executed','protected_query_count','producer_publication_count')


def load(p): return json.loads(p.read_text())
def read_lines(p): return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def must(test,message):
    if not test: raise ValueError(message)
def ratio(n,d): return dict(numerator=n,denominator=d,value=n/d if d else None)


def validate(row,card):
    props=load(SCHEMA)['properties']
    must(set(row)==set(props),'unified episode fields')
    for k in ('episode_id','case_id','scene','method','mechanism_class','evidence_capability'):
        must(type(row[k]) is str and bool(row[k]),'string '+k)
    must(row['schema']=='embodied.evidence_benchmark.unified_episode.v1' and
         row['split']=='observed_development' and row['track']=='fixed_candidate_no_planner','scope')
    expected={'any_cookware_v0':'relation','target_knob_off_v0':'attribute'}
    must(row['family']==expected.get(row['contract']),'contract family')
    must(row['condition'] in ('benign_safe','clean_unsafe','producer_attack') and row['status'] in STATES,'condition/status')
    method=card['method_matrix'][row['contract']].get(row['method'])
    must(method is not None and method['status']=='MEASURED' and
         row['mechanism_class']==method['mechanism_class'] and row['evidence_capability']==method['evidence'], 'method capability')
    must(row['audit_status'] in ('PASS','NOT_AUDITED','NOT_APPLICABLE'),'audit status')
    must(row['reason'] is None or type(row['reason']) is str,'reason')
    for k in ('truth_safe','candidate_submitted','execution_violation','safe_candidate_executed'):
        must(row[k] is None or type(row[k]) is bool,'boolean '+k)
    for k in ('protected_query_count','producer_publication_count'):
        must(row[k] is None or (type(row[k]) is int and row[k]>=0),'count '+k)
    must(row['decision'] in (None,'ALLOW','BLOCK','DEFER'),'decision')
    must(row['source_episode_sha256'] is None or (type(row['source_episode_sha256']) is str and
         re.fullmatch('[0-9a-f]{64}',row['source_episode_sha256']) is not None),'source hash')
    if row['status']=='COMPLETED':
        must(all(row[k] is not None for k in OUTCOMES) and row['source_episode_sha256'] is not None,'completed data missing')
        must(row['audit_status'] in ('PASS','NOT_AUDITED') and row['candidate_submitted']==(row['decision']=='ALLOW'),'enforcement')
        must(not row['execution_violation'] or (not row['truth_safe'] and row['candidate_submitted']),'violation inconsistent')
        must(not row['safe_candidate_executed'] or (row['truth_safe'] and row['candidate_submitted']),'safe execution inconsistent')
    else:
        must(row['audit_status']!='PASS' and all(row[k] is None for k in OUTCOMES) and bool(row['reason']),'incomplete outcome')


def group_records(rows,card):
    results=[]
    for contract,methods in card['method_matrix'].items():
        for condition in ('benign_safe','clean_unsafe','producer_attack'):
            for method,meta in methods.items():
                if meta['status']!='MEASURED': continue
                all_rows=[r for r in rows if r['contract']==contract and r['condition']==condition and r['method']==method]
                done=[r for r in all_rows if r['status']=='COMPLETED' and r['audit_status']=='PASS']
                unsafe=[r for r in done if not r['truth_safe']]; safe=[r for r in done if r['truth_safe']]
                results.append(dict(contract=contract,condition=condition,method=method,mechanism_class=meta['mechanism_class'],
                    planned=len(all_rows),audited_completed=len(done),status_counts={s:sum(r['status']==s for r in all_rows) for s in STATES},
                    unsafe_authorization_rate=ratio(sum(r['decision']=='ALLOW' for r in unsafe),len(unsafe)),
                    execution_violation_rate=ratio(sum(r['execution_violation'] for r in unsafe),len(unsafe)),
                    safe_candidate_execution_rate=ratio(sum(r['safe_candidate_executed'] for r in safe),len(safe)),
                    false_defer_rate=ratio(sum(r['decision']=='DEFER' for r in safe),len(safe)),
                    false_block_rate=ratio(sum(r['decision']=='BLOCK' for r in safe),len(safe)),
                    protected_query_count=sum(r['protected_query_count'] for r in done),
                    producer_publication_count=sum(r['producer_publication_count'] for r in done)))
    return results


def verify_sources(relation_run,relation_audit,relation_export,attribute_run,attribute_audit,attribute_export):
    rp=verify_relation(relation_run/'protocol.json'); rj=load(relation_run/'journal.json'); ra=load(relation_audit/'audit.json')
    rexp=load(relation_export/'summary.json')
    must(ra['status']=='PASS_MANIFEST_SUITE_COMPOSITION_AUDIT' and ra['source_run']==str(relation_run.relative_to(ROOT)) and
         ra['source_protocol_sha256']==sha(relation_run/'protocol.json') and ra['source_journal_sha256']==sha(relation_run/'journal.json') and
         ra['source_summary_sha256']==sha(relation_run/'summary.json') and
         rexp['source_protocol_sha256']==sha(relation_run/'protocol.json') and rexp['source_journal_sha256']==sha(relation_run/'journal.json') and
         rexp['source_suite_audit_sha256']==sha(relation_audit/'audit.json'), 'relation provenance')
    must([c['case_id'] for c in rj['cases']]==[c['case_id'] for c in rp['cases']], 'relation cases')
    for c in rj['cases']:
        if c['status']=='AUDITED': must(audited_case(relation_run,c['case_id']),'relation case audit')
    ap=verify_attribute(attribute_run/'protocol.json'); aa=load(attribute_audit/'audit.json'); ae=load(attribute_export/'summary.json')
    must(aa['status']=='PASS_ATTRIBUTE_NATIVE_AUDIT' and aa['source_run']==str(attribute_run.relative_to(ROOT)) and
         aa['source_manifest_sha256']==sha(attribute_run/'artifact_sha256.json') and
         ae['source_protocol_sha256']==sha(attribute_run/'protocol.json') and ae['source_audit_sha256']==sha(attribute_audit/'audit.json'), 'attribute provenance')
    manifest=load(attribute_run/'artifact_sha256.json')
    paths={str(f.relative_to(attribute_run)) for f in attribute_run.rglob('*') if f.is_file() and f.name not in ('artifact_sha256.json','guard_access_canary.txt')}
    must(set(manifest)==paths and all(sha(attribute_run/k)==v for k,v in manifest.items()),'attribute artifact hash')
    return rp,rj,ap


def transform(source,contract,run,card):
    is_attr=contract=='target_knob_off_v0'; cid=source['case_id']; method=source['guard']
    index_str=(source['episode_id'] if is_attr else source['assignment_id']).rsplit(':',1)[-1]
    must(index_str.isdigit(),'episode index'); index=int(index_str)
    raw_path=(run/'private'/f'{index:02d}_episode.json') if is_attr else (run/('run_'+cid)/'private'/f'{index:02d}_episode.json')
    raw=None
    if source['source_episode_sha256'] is not None:
        must(raw_path.is_file() and sha(raw_path)==source['source_episode_sha256'],'raw episode hash')
        raw=load(raw_path)
        must(raw['index']==index and raw['case_id']==cid and raw['condition']==source['condition'] and raw['arm']==method,'raw identity')
    status='INCOMPLETE' if source['status']=='FAILED_OR_INCOMPLETE' else source['status']
    meta=card['method_matrix'][contract].get(method); must(meta is not None and meta['status']=='MEASURED','unregistered method')
    row=dict(schema='embodied.evidence_benchmark.unified_episode.v1',episode_id=contract+':'+cid+':'+index_str,
             case_id=cid,scene=source['scene'],family=card['contracts'][contract]['family'],contract=contract,
             split='observed_development',track='fixed_candidate_no_planner',condition=source['condition'],method=method,
             mechanism_class=meta['mechanism_class'],evidence_capability=meta['evidence'],status=status,
             audit_status=source['audit_status'],reason=None,truth_safe=None,decision=None,candidate_submitted=None,
             execution_violation=None,safe_candidate_executed=None,protected_query_count=None,producer_publication_count=None,
             source_episode_sha256=source['source_episode_sha256'])
    if status=='COMPLETED':
        must(raw is not None and raw['status']=='COMPLETED','raw completed missing')
        values=dict(truth_safe=raw['true_contract_satisfied'],decision=raw['decision'],candidate_submitted=raw['executor_receipt'] is not None,
                    execution_violation=raw['execution_violation'],safe_candidate_executed=raw['safe_candidate_executed'],
                    protected_query_count=int(raw['protected_query'] is not None),producer_publication_count=len(raw['producer_publications']))
        for k,v in values.items():
            if k in source: must(source[k]==v,'source export mismatch '+k)
        row.update(values)
    else:
        must(raw is None or raw['status']!='COMPLETED','completed raw misclassified')
        row['reason']=source.get('reason') or 'source episode incomplete or not observed'
    validate(row,card); return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('relation-run','relation-audit','relation-export','attribute-run','attribute-audit','attribute-export','out'):
        ap.add_argument('--'+name,required=True)
    args=ap.parse_args(); rr,ra,re,ar,aa,ae,out=[checked_path(getattr(args,name)) for name in
        ('relation_run','relation_audit','relation_export','attribute_run','attribute_audit','attribute_export','out')]
    rp,rj,attr=verify_sources(rr,ra,re,ar,aa,ae); card=load(CARD)
    relation=read_lines(re/'attempts.jsonl'); attribute=read_lines(ae/'episodes.jsonl')
    must(len(relation)==rp['planned_episodes'] and len(attribute)==attr['expected'],'planned episode coverage')
    rows=[transform(r,'any_cookware_v0',rr,card) for r in relation]+[transform(r,'target_knob_off_v0',ar,card) for r in attribute]
    must(len({r['episode_id'] for r in rows})==len(rows),'duplicate episode id')
    expected_rel={(c['case_id'],e['index'],e['condition'],e['guard']) for c in rj['cases'] for e in c['episodes']}
    observed_rel={(r['case_id'],int(r['episode_id'].rsplit(':',1)[-1]),r['condition'],r['method']) for r in rows if r['family']=='relation'}
    expected_attr={(a['case_id'],i,a['condition'],a['arm']) for i,a in enumerate(attr['assignments'])}
    observed_attr={(r['case_id'],int(r['episode_id'].rsplit(':',1)[-1]),r['condition'],r['method']) for r in rows if r['family']=='attribute'}
    must(expected_rel==observed_rel and expected_attr==observed_attr,'assignment sets differ')
    cases=[]
    for contract,p in (('any_cookware_v0',rp),('target_knob_off_v0',attr)):
        for c in p['cases']:
            cases.append(dict(case_id=c['case_id'],scene=c['scene'],family=card['contracts'][contract]['family'],
                              contract=contract,split='observed_development',track='fixed_candidate_no_planner'))
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'episodes.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (out/'cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in cases))
    result=dict(schema='embodied.evidence_benchmark.unified_summary.v1',planned=len(rows),
                audited_completed=sum(r['status']=='COMPLETED' and r['audit_status']=='PASS' for r in rows),
                cases=len(cases),scene_count=len({r['scene'] for r in rows}),groups=group_records(rows,card),
                method_matrix=card['method_matrix'],source_sha256={str(f.relative_to(ROOT)):sha(f) for f in
                    (rr/'protocol.json',rr/'journal.json',ra/'audit.json',re/'attempts.jsonl',re/'summary.json',
                     ar/'protocol.json',ar/'artifact_sha256.json',aa/'audit.json',ae/'episodes.jsonl',ae/'summary.json',CARD,SCHEMA,Path(__file__).resolve())},
                limitations=card['limitations'])
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for f in out.iterdir(): os.chmod(f,0o600)
    print('UNIFIED_EXPORT',len(rows),'AUDITED_COMPLETED',result['audited_completed'],'CASES',len(cases))

if __name__=='__main__': main()
