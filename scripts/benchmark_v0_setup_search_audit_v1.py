"""Audit recorded setup search ordering, actions and reported truth predicates."""
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
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--run',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); run,out=checked_path(args.run),checked_path(args.out)
    p=load(run/'protocol.json'); d=load(run/'results.json')
    must(d['status']=='FINISHED' and d['source_protocol_sha256']==sha(run/'protocol.json'), 'protocol/result')
    for path,expected in p['source_sha256'].items(): must(sha(ROOT/path)==expected, 'source hash: '+path)
    must([s['scene'] for s in d['scenes']]==[x['scene'] for x in p['cases']], 'scene list')
    total=0
    for s,base in zip(d['scenes'],p['cases']):
        must(s['pan_id']==base['pan_id'], 'target pan')
        pairs=[(x['knob_id'],x['burner_id']) for x in s['eligible_pairs']]
        must(pairs==sorted(pairs) and len(pairs)==len(set(pairs)), 'pair order')
        attempts=s['attempts']; must(0<len(attempts)<=p['max_pairs_per_scene'], 'attempt count')
        must([(x['case']['knob_id'],x['case']['burner_id']) for x in attempts]==pairs[:len(attempts)], 'not a pair prefix')
        for i,a in enumerate(attempts):
            c=a['case']; total+=1
            must(c['scene']==s['scene'] and c['pan_id']==s['pan_id'] and c['family']=='relation', 'case binding')
            receipts=a.get('setup_receipts',[])
            reqs=[{'action':'PickupObject','objectId':c['pan_id'],'forceAction':True},
                  {'action':'PutObject','objectId':c['burner_id'],'forceAction':True,'placeStationary':True}]
            must(len(receipts)<=2 and all(r['request']==reqs[k] for k,r in enumerate(receipts)), 'setup actions')
            for key in ('setup_navigation','drift_navigation','candidate_navigation'):
                for r in a.get(key,{}).get('receipts',[]):
                    must(r['request']['action']=='TeleportFull' and not r['request'].get('forceAction',False), 'navigation action')
            if 'drift_receipt' in a:
                must(a['drift_receipt']['request']=={'action':'PickupObject','objectId':c['pan_id'],'forceAction':False},'drift action')
            if a['status']=='FEASIBLE':
                must(i==len(attempts)-1 and s['status']=='FEASIBLE' and s['selected']==c, 'first feasible')
                must(a['reset_success'] and len(receipts)==2 and all(r['success'] for r in receipts), 'setup success')
                must(all(a[k]['success'] for k in ('setup_navigation','drift_navigation','candidate_navigation')) and
                     a['drift_receipt']['success'], 'navigation/drift success')
                safe,unsafe=a['safe_truth'],a['unsafe_truth']
                must(safe['knob_on'] is False and unsafe['knob_on'] is False and
                     safe['controlled']==unsafe['controlled']==[c['burner_id']] and
                     c['pan_id'] in safe['cookware_on_target'] and c['burner_id'] in (safe['target_parents'] or []) and
                     not unsafe['cookware_on_target'] and c['burner_id'] not in (unsafe['target_parents'] or []), 'truth predicates')
                must(len(a['safe_snapshot_sha256'])==len(a['unsafe_snapshot_sha256'])==64, 'snapshot hashes')
            else:
                must(a['status']=='SETUP_INFEASIBLE' and bool(a.get('error')), 'failed attempt reason')
        if s['status']=='FEASIBLE': must(attempts[-1]['status']=='FEASIBLE','selected missing')
        elif s['status']=='NO_FEASIBLE_PAIR': must(len(attempts)==min(p['max_pairs_per_scene'],len(pairs)), 'incomplete search')
        else: raise ValueError('scene error or incomplete')
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    report=dict(status='PASS_SETUP_RECORD_AUDIT',scenes=len(d['scenes']),attempts=total,
                source_protocol_sha256=sha(run/'protocol.json'),source_results_sha256=sha(run/'results.json'),
                auditor_sha256=sha(Path(__file__).resolve()),
                limitations=['Does not independently replay Unity or verify reported truth snapshots; only hashes are retained',
                             'Checks recorded receipts; it is not an exhaustive system call trace',
                             'Navigation action receipts are saved after approach returns; abrupt interruption may lose in-flight receipts',
                             'Scene layouts and outcomes are development observations, not a held-out evaluation'])
    path=out/'audit.json'; path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); os.chmod(path,0o600)
    print(report['status'],report['scenes'],'scenes',report['attempts'],'attempts')

if __name__=='__main__': main()
