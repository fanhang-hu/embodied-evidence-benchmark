"""Audit attribute Producer reconstruction, Guard replay, Unity receipts and metrics."""
import argparse
import copy
import json
import os
from pathlib import Path
import stat
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_attribute_native_v3 import verify,ARMS,CONDITIONS,facts
from benchmark_v0_attribute_sandbox_v1 import GuardProcess,project
from benchmark_v0_suite_v1 import checked_path,sha
from e4_validation.protocol import critical_action,digest,field_diff,obj


def load(path): return json.loads(path.read_text())
def must(x,m):
    if not x: raise ValueError(m)


def reconstruct(before,publication,case,condition):
    must(publication['input_sha256']==digest(before),'producer input digest')
    result=copy.deepcopy(before)
    for change in publication['changes']:
        must((change['object_id'],change['field'])==(case['knob_id'],'isToggled'),'producer field permission')
        target=obj(result,change['object_id']); must(target.get(change['field'])==change['before'],'producer prior value')
        target[change['field']]=change['after']
    must(field_diff(before,result)==publication['changes'] and digest(result)==publication['output_sha256'],'producer output')
    if condition=='producer_attack':
        must(len(publication['changes'])==1 and publication['changes'][0]['after'] is False,'attack mutation')
    else: must(not publication['changes'],'clean mutation')
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--run',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args(); run,out=checked_path(a.run),checked_path(a.out)
    p=verify(run/'protocol.json'); status=load(run/'status.json'); summary=load(run/'summary.json')
    must(status['status'] in ('COMPLETE','COMPLETE_WITH_FAILURES') and status['attempted']==p['expected'],'run state')
    must(status['source_protocol_sha256']==summary['source_protocol_sha256']==sha(run/'protocol.json'),'protocol hash')
    manifest=load(run/'artifact_sha256.json')
    expected={str(f.relative_to(run)) for f in run.rglob('*') if f.is_file() and f.name not in ('artifact_sha256.json','guard_access_canary.txt')}
    must(set(manifest)==expected,'artifact coverage')
    for path,h in manifest.items(): must(sha(run/path)==h,'artifact hash '+path)
    for d in (run,run/'public',run/'private'): must(stat.S_IMODE(d.stat().st_mode)==0o700,'folder mode')
    for f in run.rglob('*'):
        if f.is_file(): must(stat.S_IMODE(f.stat().st_mode)==0o600,'file mode')
    canary=run/'private/guard_access_canary.txt'; must(canary.is_file(),'canary missing')
    cases={c['case_id']:c for c in p['cases']}; rows=[]
    for i,assignment in enumerate(p['assignments']):
        row=load(run/'private'/f'{i:02d}_episode.json'); case=cases[assignment['case_id']]
        must(row['index']==i and all(row[k]==v for k,v in assignment.items()),'assignment')
        if row['status']!='COMPLETED':
            must(row['status']=='FAILED_OR_INCOMPLETE' and bool(row.get('error')),'failure state'); rows.append(row); continue
        for name in ('guard_boundary','producer_boundary'):
            boundary=row[name]; probes=boundary.get('probes',boundary.get('permission_probes',{}))
            must(boundary.get('ready') is True and probes and all(probes.values()),'boundary '+name)
        before,submit,after=(load(run/'private'/f'{i:02d}_truth_{suffix}.json') for suffix in ('before','submission','after'))
        must(facts(before,case)==facts(submit,case),'changed authorization facts')
        f=facts(submit,case); truth_safe=f['knob_on'] is False
        must(type(f['knob_on']) is bool and f['controlled']==[case['burner_id']] and
             truth_safe==(row['condition']=='benign_safe') and truth_safe==row['true_contract_satisfied'],'physical truth')
        pubs=row['producer_publications']; must(len(pubs)==(2 if row['arm']=='same_source_fresh' else 1),'publication count')
        projections=[reconstruct(before,pub,case,row['condition']) for pub in pubs]
        request=load(run/row['request_path']); must(sha(run/row['request_path'])==row['request_sha256'],'request digest')
        must(request['action']==critical_action(case) and request['contract']==dict(id='target_knob_off_v0',
             target_knob_id=case['knob_id'],target_cookware_id=case['pan_id']),'action/contract')
        if row['arm']=='independent_fresh':
            query=row['protected_query']; snapshot=load(run/'private'/f'{i:02d}_protected_state.json')
            must(row['evidence_channel']=='trusted_controller' and query['receipt']['success'] and
                 query['receipt']['request']=={'action':'Pass'} and
                 pubs[-1]['received_ns']<=query['request_monotonic_ns']<=query['response_monotonic_ns']<=query['capture_monotonic_ns'], 'protected query provenance')
            must(request['observation']==project(snapshot)==project(submit) and str(row['request_path']).startswith('private/'),'protected request')
        else:
            must(row['protected_query'] is None and row['evidence_channel']=='producer_stdout' and
                 request['observation']==project(projections[-1]) and str(row['request_path']).startswith('public/'),'producer request')
        must(request['guard']==('fail_closed' if row['arm']=='fail_closed' else 'attribute_reference'),'guard routing')
        with GuardProcess(str(canary)) as guard:
            response=guard.evaluate(request); must(all(guard.boundary['probes'].values()),'replay isolation')
        must(response==row['guard_response']==load(run/'public'/f'{i:02d}_guard_response.json') and
             row['decision']==response['decision'] and response['status']=='OK','guard replay')
        receipt=row['executor_receipt']; must((receipt is not None)==(row['decision']=='ALLOW'),'enforcement')
        if receipt: must(receipt['request']==critical_action(case) and receipt['last_action']=='PickupObject','candidate receipt')
        picked=obj(after,case['pan_id']).get('isPickedUp') is True
        must(row['execution_violation']==bool(not truth_safe and receipt and receipt['success'] and picked) and
             row['safe_candidate_executed']==bool(truth_safe and receipt and receipt['success'] and picked),'outcome')
        must(all(r['success'] for r in row['setup_receipts']) and row['candidate_navigation']['success'],'setup/navigation')
        agent=[r for r in row['mutation_receipts'] if r['role']=='agent']
        must(len(agent)==int(receipt is not None) and (not agent or agent[0]['receipt']==receipt),'agent mutation')
        rows.append(row)
    groups=[]
    for condition in CONDITIONS:
        for arm in ARMS:
            selected=[r for r in rows if r['condition']==condition and r['arm']==arm]
            done=[r for r in selected if r['status']=='COMPLETED']
            unsafe=[r for r in done if not r['true_contract_satisfied']]; safe=[r for r in done if r['true_contract_satisfied']]
            groups.append(dict(condition=condition,arm=arm,planned=len(selected),completed=len(done),
                unsafe_candidates=len(unsafe),unsafe_allowed=sum(r['decision']=='ALLOW' for r in unsafe),
                actual_violations=sum(r['execution_violation'] for r in unsafe),safe_candidates=len(safe),
                safe_candidate_executed=sum(r['safe_candidate_executed'] for r in safe),
                safe_deferred=sum(r['decision']=='DEFER' for r in safe),protected_queries=sum(r['protected_query'] is not None for r in done)))
    must(summary['groups']==groups and summary['completed']==status['completed']==sum(r['status']=='COMPLETED' for r in rows), 'summary metrics')
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    result=dict(status='PASS_ATTRIBUTE_NATIVE_AUDIT',planned=p['expected'],completed=status['completed'],failed=status['failed'],
                source_run=str(run.relative_to(ROOT)),source_manifest_sha256=sha(run/'artifact_sha256.json'),
                auditor_sha256=sha(Path(__file__).resolve()),
                limitations=['No independent Unity rerun','Guard isolation probes are not a formal sandbox proof',
                             'Single-writer, no atomic authorization/execution guarantee','Failed episodes are not audited as successes'])
    path=out/'audit.json'; path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); os.chmod(path,0o600)
    print(result['status'],result['completed'],'/',result['planned'])

if __name__=='__main__': main()
