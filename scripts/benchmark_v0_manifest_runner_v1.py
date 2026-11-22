"""Run frozen observed-development relation manifests using adapted audited V0 pilot.

Adds private setup traces and failure snapshots while preserving original pilot
and audit code. Case metadata injection and setup adaptation are explicit.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import random
import re
import signal
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import ARMS, CONDITIONS, checked_path, hashes, sha
from benchmark_v0_supervised_suite_v2 import atomic_json, terminate_handler
from benchmark_v0_episode_supervisor_v1 import monitor
from benchmark_v0_attempts_v2 import audited_case

SOURCE=Path(__file__).resolve()
EXTRA=[SOURCE,ROOT/'scripts/benchmark_v0_episode_supervisor_v1.py',
       ROOT/'scripts/benchmark_v0_supervised_suite_v2.py',ROOT/'scripts/benchmark_v0_attempts_v2.py']
SEED=260626


def source_hashes(case_path):
    h=hashes(); h.update({str(p.relative_to(ROOT)):sha(p) for p in [*EXTRA,case_path]}); return h


def read_cases(path):
    records=[json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    if not records: raise ValueError('empty case manifest')
    keys=('case_id','scene','family','pan_id','burner_id','knob_id')
    cases=[]
    for r in records:
        if r.get('split')!='observed_development' or r.get('family')!='relation':
            raise ValueError('only observed development relation cases are supported')
        c={k:r[k] for k in keys}
        if any(not isinstance(v,str) or not v for v in c.values()): raise ValueError('invalid case field')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',c['case_id']) or not re.fullmatch(r'FloorPlan[0-9]+',c['scene']):
            raise ValueError('invalid case or scene ID')
        cases.append(c)
    if len({c['case_id'] for c in cases})!=len(cases): raise ValueError('duplicate case ID')
    return cases


def verify_protocol(path):
    p=json.loads(path.read_text()); manifest=checked_path(p['case_manifest'])
    if p.get('schema')!='embodied.evidence_benchmark.manifest_run.v1' or p['source_sha256']!=source_hashes(manifest):
        raise ValueError('source/protocol mismatch')
    if p['cases']!=read_cases(manifest) or p['conditions']!=list(CONDITIONS) or p['guards']!=list(ARMS) or p['seed']!=SEED:
        raise ValueError('cases/matrix mismatch')
    if p['planned_episodes']!=len(p['cases'])*12: raise ValueError('planned count')
    return p


def freeze(a):
    manifest=checked_path(a.cases); cases=read_cases(manifest)
    p=dict(schema='embodied.evidence_benchmark.manifest_run.v1',split='observed_development',
           case_manifest=str(manifest.relative_to(ROOT)),cases=cases,conditions=list(CONDITIONS),guards=list(ARMS),
           seed=SEED,planned_episodes=len(cases)*12,contract='any_cookware_v0',track='fixed_candidate_no_planner',
           episode_timeout_from_observed_start_seconds=60,case_timeout_seconds=180,
           case_adapter='inject frozen manifest case into existing pilot and auditor catalogue readers',
           setup_adapter='equivalent setup action sequence with extra private receipts and failure snapshots',
           failure_rule='preserve failure and unknown assignments, continue next case; no retries or substitutions',
           source_sha256=source_hashes(manifest),
           limitations=['Only relation and four fixed guards; no arbitrary plugin API',
                        'Completed episodes retain private before/submission/after truth snapshots',
                        'Setup failures have supplemental snapshots; other failure phases may have incomplete snapshots',
                        'Audit and pilot share injected case and setup adapter; not end-to-end official external controller',
                        'Observed development only; no independent held-out or full-task claim'])
    out=checked_path(a.out); out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    atomic_json(out/'protocol.json',p); print('MANIFEST_PROTOCOL_FROZEN',out/'protocol.json',flush=True)


def traced_prepare(controller,scene,pan_id,burner_id,knob_id,occupied,active,run_dir):
    """Equivalent prepare; snapshot and log when setup fails, inside evaluator only."""
    from e4_validation.simulator import objects,by_id,step,approach
    index=json.loads((run_dir/'status.json').read_text())['attempted']-1
    path=run_dir/'private'/f'{index:02d}_setup_trace.json'
    trace=dict(schema='embodied.evidence_benchmark.setup_trace.v1',index=index,status='STARTED',
               scene=scene,pan_id=pan_id,burner_id=burner_id,knob_id=knob_id,receipts=[])
    def persist(): atomic_json(path,trace)
    persist()
    try:
        controller.reset(scene=scene)
        trace['reset_success']=bool(controller.last_event.metadata['lastActionSuccess']); persist()
        initial=objects(controller); pan=by_id(initial,pan_id)
        assert pan['objectType'] in ('Pan','Pot')
        assert all(not o.get('isToggled') for o in initial if o['objectType']=='StoveKnob')
        if occupied:
            for req in (dict(action='PickupObject',objectId=pan_id,forceAction=True),
                        dict(action='PutObject',objectId=burner_id,forceAction=True,placeStationary=True)):
                receipt=step(controller,req,trace['receipts']); persist()
                assert receipt['success'],receipt
            assert burner_id in (by_id(objects(controller),pan_id).get('parentReceptacles') or [])
        else:
            assert burner_id not in (pan.get('parentReceptacles') or [])
            assert not by_id(initial,burner_id).get('receptacleObjectIds')
        if active:
            try: nav=approach(controller,knob_id,trace['receipts'])
            finally: persist()
            assert nav, 'Cannot approach knob for setup'
            receipt=step(controller,dict(action='ToggleObjectOn',objectId=knob_id,forceAction=False),trace['receipts']); persist()
            assert receipt['success'],receipt
        target=pan_id if occupied else knob_id
        try: nav=approach(controller,target,trace['receipts'])
        finally: persist()
        assert nav, f'Cannot approach {target}'
        trace['status']='COMPLETE'; persist(); return trace['receipts']
    except Exception as exc:
        trace.update(status='FAILED_OR_INCOMPLETE',error=repr(exc))
        try:
            trace['failure_snapshot']={'objects':objects(controller)}
        except Exception as capture_exc:
            trace['snapshot_capture_error']=repr(capture_exc)
        persist(); raise


def child(a):
    p=verify_protocol(checked_path(a.protocol)); matches=[c for c in p['cases'] if c['case_id']==a.case]
    if len(matches)!=1: raise ValueError('unknown case')
    case=matches[0]; run=checked_path(a.run)
    import benchmark_v0_external_native as pilot
    import benchmark_v0_external_native_audit as audit
    pilot.read_jsonl=lambda ignored:[case]
    pilot.prepare=lambda controller,scene,pan_id,burner_id,knob_id,occupied,active: traced_prepare(
        controller,scene,pan_id,burner_id,knob_id,occupied,active,run)
    pilot.CASE_ID=case['case_id']; pilot.OUT=run; pilot.main()
    audit.read_jsonl=lambda ignored:[case]
    audit.RUN=run; audit.OUT=checked_path(a.audit); audit.main()


def aggregate(cases,out):
    result=[]
    for condition in CONDITIONS:
        for arm in ARMS:
            rows=[]
            for c in cases:
                if c['status']!='AUDITED': continue
                summary=json.loads((out/('run_'+c['case_id'])/'summary.json').read_text())
                matching=[r for r in summary['groups'] if r['condition']==condition and r['arm']==arm]
                if len(matching)!=1: raise ValueError('missing case group')
                rows.extend(matching)
            fields=('unsafe_candidates','unsafe_allowed','actual_violations','safe_candidates',
                    'safe_candidate_executed','safe_deferred','protected_queries')
            result.append(dict(condition=condition,guard=arm,planned=len(cases),audited_completed=len(rows),
                               **{k:sum(x[k] for x in rows) for k in fields}))
    return result


def run(a):
    protocol=checked_path(a.protocol); p=verify_protocol(protocol); out=checked_path(a.out)
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'protocol.json').write_bytes(protocol.read_bytes()); os.chmod(out/'protocol.json',0o600)
    cases=[]
    for c in p['cases']:
        assignments=[dict(condition=x,guard=y) for x in CONDITIONS for y in ARMS]; random.Random(SEED).shuffle(assignments)
        episodes=[dict(assignment_id=f"{c['case_id']}:{i:02d}",case_id=c['case_id'],scene=c['scene'],index=i,
                       status='PLANNED',audit_status='NOT_YET_VERIFIED',**v) for i,v in enumerate(assignments)]
        cases.append(dict(case_id=c['case_id'],scene=c['scene'],status='PLANNED',episodes=episodes))
    state=dict(schema='embodied.evidence_benchmark.manifest_run_journal.v1',status='STARTED',
               source_protocol_sha256=sha(protocol),planned_episodes=p['planned_episodes'],cases=cases,start_wall_ns=time.time_ns())
    def persist(): atomic_json(out/'journal.json',state)
    persist(); old={s:signal.signal(s,terminate_handler) for s in (signal.SIGTERM,signal.SIGHUP)}; current=None
    try:
        for current in cases:
            cid=current['case_id']; case_dir=out/('run_'+cid); audit_dir=out/('audit_'+cid)
            current.update(status='STARTED',start_wall_ns=time.time_ns()); persist(); print('MANIFEST_CASE_STARTED',cid,flush=True)
            cmd=[sys.executable,'-B',str(SOURCE),'child','--protocol',str(protocol),'--case',cid,'--run',str(case_dir),'--audit',str(audit_dir)]
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LIBGL_ALWAYS_SOFTWARE':'1'}
            try:
                res=monitor(cmd,case_dir,current['episodes'],out/('case_'+cid+'.log'),
                            p['episode_timeout_from_observed_start_seconds'],p['case_timeout_seconds'],persist,env=env)
                current.update(res,finished_wall_ns=time.time_ns())
                if res['status']=='EXITED_ZERO':
                    if not audited_case(out,cid): current['status']='AUDIT_MISSING'
                    elif any(r['status']!='COMPLETED_RECORDED' for r in current['episodes']): current['status']='JOURNAL_MISMATCH'
                    else:
                        current.update(status='AUDITED',audit_sha256=sha(audit_dir/'audit.json'),
                                       manifest_sha256=sha(case_dir/'artifact_sha256.json'))
                        for r in current['episodes']: r['audit_status']='PASS'
            except Exception as exc:
                current.update(status='SUPERVISOR_ERROR',error=repr(exc),traceback=traceback.format_exc())
            for r in current['episodes']:
                if r['status'] in ('PLANNED','RUNNING_OBSERVED'): r.update(status='UNKNOWN',reason='no terminal record')
            persist(); print('MANIFEST_CASE_STATUS',cid,current['status'],flush=True)
        state['status']='COMPLETE' if all(c['status']=='AUDITED' for c in cases) else 'COMPLETE_WITH_FAILURES'
    except KeyboardInterrupt as exc:
        state.update(status='INTERRUPTED',interruption=str(exc))
        if current and current['status']=='STARTED': current['status']='INTERRUPTED'
    except Exception as exc:
        state.update(status='FAILED',error=repr(exc),traceback=traceback.format_exc())
    finally:
        if current and current['status']!='PLANNED':
            for r in current['episodes']:
                if r['status'] in ('PLANNED','RUNNING_OBSERVED'): r.update(status='UNKNOWN',reason='no terminal record')
        state['end_wall_ns']=time.time_ns(); persist()
        for s,h in old.items(): signal.signal(s,h)
    result=dict(schema='embodied.evidence_benchmark.manifest_summary.v1',status=state['status'],
                source_protocol_sha256=sha(protocol),journal_sha256=sha(out/'journal.json'),
                planned_cases=len(cases),audited_cases=sum(c['status']=='AUDITED' for c in cases),
                planned_episodes=p['planned_episodes'],cases=[dict(case_id=c['case_id'],scene=c['scene'],status=c['status']) for c in cases],
                groups=aggregate(cases,out),limitations=p['limitations'])
    atomic_json(out/'summary.json',result); print('MANIFEST_RUN_STATUS',state['status'],flush=True)
    return 0 if state['status']=='COMPLETE' else 1


def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='command',required=True)
    x=sub.add_parser('freeze'); x.add_argument('--cases',required=True); x.add_argument('--out',required=True); x.set_defaults(func=freeze)
    x=sub.add_parser('run'); x.add_argument('--protocol',required=True); x.add_argument('--out',required=True); x.set_defaults(func=run)
    x=sub.add_parser('child'); x.add_argument('--protocol',required=True); x.add_argument('--case',required=True); x.add_argument('--run',required=True); x.add_argument('--audit',required=True); x.set_defaults(func=child)
    a=ap.parse_args(); ret=a.func(a); return ret if isinstance(ret,int) else 0

if __name__=='__main__': sys.exit(main())
