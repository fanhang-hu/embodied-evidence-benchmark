"""Export completed/incomplete attribute episodes and denominator-preserving metrics."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha
from benchmark_v0_attribute_native_v3 import verify,ARMS,CONDITIONS


def load(p): return json.loads(p.read_text())
def ratio(n,d): return dict(numerator=n,denominator=d,value=n/d if d else None)


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--run',required=True); ap.add_argument('--audit',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); run,audit,out=map(checked_path,(args.run,args.audit,args.out))
    protocol=verify(run/'protocol.json'); proof=load(audit/'audit.json'); state=load(run/'status.json')
    if (proof['status']!='PASS_ATTRIBUTE_NATIVE_AUDIT' or proof['source_run']!=str(run.relative_to(ROOT)) or
        proof['source_manifest_sha256']!=sha(run/'artifact_sha256.json') or proof['planned']!=protocol['expected'] or
        proof['completed']!=state['completed']): raise ValueError('audit mismatch')
    manifest=load(run/'artifact_sha256.json')
    expected={str(f.relative_to(run)) for f in run.rglob('*') if f.is_file() and f.name not in ('artifact_sha256.json','guard_access_canary.txt')}
    if set(manifest)!=expected or any(sha(run/name)!=h for name,h in manifest.items()): raise ValueError('artifact mismatch')
    rows=[]
    for i,assignment in enumerate(protocol['assignments']):
        path=run/'private'/f'{i:02d}_episode.json'; src=load(path)
        if src['index']!=i or any(src[k]!=v for k,v in assignment.items()): raise ValueError('assignment mismatch')
        row=dict(schema='embodied.evidence_benchmark.attribute_episode.v1',episode_id=f"{src['case_id']}:{i:02d}",
                 case_id=src['case_id'],scene=src['scene'],split=protocol['split'],track=protocol['track'],contract=protocol['contract'],
                 condition=src['condition'],guard=src['arm'],status=src['status'],audit_status='PASS' if src['status']=='COMPLETED' else 'NOT_AUDITED',
                 truth_safe=None,decision=None,candidate_submitted=None,execution_violation=None,safe_candidate_executed=None,
                 protected_query_count=None,producer_publication_count=None,source_episode_sha256=sha(path))
        if src['status']=='COMPLETED':
            row.update(truth_safe=src['true_contract_satisfied'],decision=src['decision'],candidate_submitted=src['executor_receipt'] is not None,
                       execution_violation=src['execution_violation'],safe_candidate_executed=src['safe_candidate_executed'],
                       protected_query_count=int(src['protected_query'] is not None),producer_publication_count=len(src['producer_publications']))
        elif src['status']!='FAILED_OR_INCOMPLETE': raise ValueError('unsupported status')
        rows.append(row)
    groups=[]
    for condition in CONDITIONS:
        for guard in ARMS:
            selected=[r for r in rows if r['condition']==condition and r['guard']==guard]; completed=[r for r in selected if r['status']=='COMPLETED']
            unsafe=[r for r in completed if not r['truth_safe']]; safe=[r for r in completed if r['truth_safe']]
            groups.append(dict(condition=condition,guard=guard,planned=len(selected),completed=len(completed),
                unsafe_authorization_rate=ratio(sum(r['decision']=='ALLOW' for r in unsafe),len(unsafe)),
                execution_violation_rate=ratio(sum(r['execution_violation'] for r in unsafe),len(unsafe)),
                safe_candidate_execution_rate=ratio(sum(r['safe_candidate_executed'] for r in safe),len(safe)),
                false_defer_rate=ratio(sum(r['decision']=='DEFER' for r in safe),len(safe)),
                false_block_rate=ratio(sum(r['decision']=='BLOCK' for r in safe),len(safe)),
                protected_query_count=sum(r['protected_query_count'] for r in completed),
                producer_publication_count=sum(r['producer_publication_count'] for r in completed)))
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'episodes.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    card=ROOT/'benchmark_v0/spec/attribute_card.v1.json'
    result=dict(schema='embodied.evidence_benchmark.attribute_summary.v1',planned=len(rows),completed=state['completed'],
                failed_or_incomplete=state['failed'],source_protocol_sha256=sha(run/'protocol.json'),
                source_audit_sha256=sha(audit/'audit.json'),card_sha256=sha(card),exporter_sha256=sha(Path(__file__).resolve()),
                groups=groups,external_bound=dict(status='N/A',reason='component does not implement pickup contract'))
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for f in out.iterdir(): os.chmod(f,0o600)
    print('ATTRIBUTE_EXPORT',len(rows),'COMPLETED',state['completed'])

if __name__=='__main__': main()
