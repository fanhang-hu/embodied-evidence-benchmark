"""Combine separately audited configurable relation and attribute runs."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha
from benchmark_v0_relation_native_v3 import verify as verify_relation
from benchmark_v0_attribute_native_v2 import verify as verify_attribute
from benchmark_v0_unified_export_v1 import validate,group_records

CARD=ROOT/'benchmark_v0/spec/unified_card.v2.json'
SCHEMA=ROOT/'benchmark_v0/spec/unified_episode.schema.v1.json'


def load(p): return json.loads(p.read_text())
def must(x,message):
    if not x: raise ValueError(message)


def read_source(run,audit,contract,card):
    is_rel=contract=='any_cookware_v0'; p=(verify_relation if is_rel else verify_attribute)(run/'protocol.json')
    status=load(run/'status.json'); proof=load(audit/'audit.json'); manifest=load(run/'artifact_sha256.json')
    expected_status='PASS_RELATION_NATIVE_AUDIT' if is_rel else 'PASS_ATTRIBUTE_NATIVE_AUDIT'
    must(proof['status']==expected_status and proof['source_run']==str(run.relative_to(ROOT)) and
         proof['source_manifest_sha256']==sha(run/'artifact_sha256.json') and
         proof['planned']==p['expected'] and proof['completed']==status['completed'],'audit binding')
    paths={str(f.relative_to(run)) for f in run.rglob('*') if f.is_file() and f.name not in ('artifact_sha256.json','guard_access_canary.txt')}
    must(set(manifest)==paths and all(sha(run/k)==v for k,v in manifest.items()),'source artifact mismatch')
    cases={c['case_id']:c for c in p['cases']}; rows=[]
    for i,assignment in enumerate(p['assignments']):
        path=run/'private'/f'{i:02d}_episode.json'; src=load(path); c=cases[assignment['case_id']]
        must(src['index']==i and all(src[k]==v for k,v in assignment.items()),'source assignment')
        method=src['arm']; spec=card['method_matrix'][contract].get(method)
        must(spec is not None and spec['status']=='MEASURED','method mismatch')
        done=src['status']=='COMPLETED'
        if not done: must(src['status']=='FAILED_OR_INCOMPLETE','unrecognized failure')
        row=dict(schema='embodied.evidence_benchmark.unified_episode.v1',episode_id=f"{contract}:{src['case_id']}:{i:02d}",
                 case_id=src['case_id'],scene=c['scene'],family=c['family'],contract=contract,split='observed_development',
                 track='fixed_candidate_no_planner',condition=src['condition'],method=method,
                 mechanism_class=spec['mechanism_class'],evidence_capability=spec['evidence'],
                 status='COMPLETED' if done else 'INCOMPLETE',audit_status='PASS' if done else 'NOT_AUDITED',
                 reason=None if done else 'source episode failed or incomplete',truth_safe=None,decision=None,
                 candidate_submitted=None,execution_violation=None,safe_candidate_executed=None,
                 protected_query_count=None,producer_publication_count=None,source_episode_sha256=sha(path))
        if done:
            row.update(truth_safe=src['true_contract_satisfied'],decision=src['decision'],
                       candidate_submitted=src['executor_receipt'] is not None,execution_violation=src['execution_violation'],
                       safe_candidate_executed=src['safe_candidate_executed'],protected_query_count=int(src['protected_query'] is not None),
                       producer_publication_count=len(src['producer_publications']))
        validate(row,card); rows.append(row)
    must(len(rows)==p['expected'] and sum(r['status']=='COMPLETED' for r in rows)==status['completed'],'coverage')
    return p,rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('relation-run','relation-audit','attribute-run','attribute-audit','out'): ap.add_argument('--'+name,required=True)
    a=ap.parse_args(); rr,ra,ar,aa,out=[checked_path(getattr(a,x)) for x in ('relation_run','relation_audit','attribute_run','attribute_audit','out')]
    card=load(CARD); rp,rrows=read_source(rr,ra,'any_cookware_v0',card); tp,trows=read_source(ar,aa,'target_knob_off_v0',card)
    rows=rrows+trows; must(len({r['episode_id'] for r in rows})==len(rows),'duplicate episodes')
    cases=[dict(case_id=c['case_id'],scene=c['scene'],family=c['family'],contract=contract,split='observed_development')
           for p,contract in ((rp,'any_cookware_v0'),(tp,'target_knob_off_v0')) for c in p['cases']]
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'episodes.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (out/'cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in cases))
    sources=(rr/'protocol.json',rr/'artifact_sha256.json',ra/'audit.json',ar/'protocol.json',ar/'artifact_sha256.json',aa/'audit.json',CARD,SCHEMA,Path(__file__).resolve())
    summary=dict(schema='embodied.evidence_benchmark.native_unified.v1',planned=len(rows),
                 audited_completed=sum(r['status']=='COMPLETED' and r['audit_status']=='PASS' for r in rows),
                 cases=len(cases),scene_count=len({r['scene'] for r in rows}),groups=group_records(rows,card),
                 method_matrix=card['method_matrix'],source_sha256={str(x.relative_to(ROOT)):sha(x) for x in sources},
                 limitations=card['limitations']+['Only successful source episodes count in metrics; failures remain visible',
                    'Runs may overlap in scene, case history and other experiments; no pooled rate or heldout claim'])
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for x in out.iterdir(): os.chmod(x,0o600)
    print('NATIVE_UNIFIED',len(rows),'AUDITED',summary['audited_completed'],'CASES',len(cases))

if __name__=='__main__': main()
