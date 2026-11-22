"""Route a frozen two-contract development plan to existing audited backends.

This is an orchestrator over fixed, pre-frozen backends; it is not an arbitrary
plugin runner or formal held-out benchmark. Stage outputs are never overwritten.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha
from benchmark_v0_manifest_runner_v1 import verify_protocol as verify_relation
from benchmark_v0_attribute_native_v1 import verify as verify_attribute
from benchmark_v0_supervised_suite_v2 import atomic_json, stop_group, terminate_handler

SOURCE=Path(__file__).resolve()
CARD=ROOT/'benchmark_v0/spec/unified_card.v1.json'
SCHEMA=ROOT/'benchmark_v0/spec/unified_episode.schema.v1.json'
SCRIPTS=['benchmark_v0_manifest_runner_v1.py','benchmark_v0_manifest_audit_v1.py','benchmark_v0_manifest_attempts_v1.py',
         'benchmark_v0_attribute_native_v1.py','benchmark_v0_attribute_audit_v1.py','benchmark_v0_attribute_export_v1.py',
         'benchmark_v0_unified_export_v1.py','benchmark_v0_unified_audit_v2.py','benchmark_v0_supervised_suite_v2.py']
STAGES=('relation_run','relation_audit','relation_export','attribute_run','attribute_audit','attribute_export','unified_export','unified_audit')


def source_hashes(relation,attribute):
    paths=[SOURCE,CARD,SCHEMA,relation,attribute]+[ROOT/'scripts'/n for n in SCRIPTS]
    return {str(p.relative_to(ROOT)):sha(p) for p in dict.fromkeys(paths)}


def build_cases(rp,ap):
    cases=[]
    for contract,family,p in (('any_cookware_v0','relation',rp),('target_knob_off_v0','attribute',ap)):
        for c in p['cases']:
            if c['family']!=family: raise ValueError('backend case family mismatch')
            cases.append(dict(case_id=c['case_id'],scene=c['scene'],family=family,contract=contract,split='observed_development'))
    if len({(c['contract'],c['case_id']) for c in cases})!=len(cases): raise ValueError('duplicate contract case')
    return cases


def plan(relation,attribute):
    rp=verify_relation(relation); ap=verify_attribute(attribute); card=json.loads(CARD.read_text())
    rmethods={k for k,v in card['method_matrix']['any_cookware_v0'].items() if v['status']=='MEASURED'}
    amethods={k for k,v in card['method_matrix']['target_knob_off_v0'].items() if v['status']=='MEASURED'}
    if set(rp['guards'])!=rmethods or set(ap['arms'])!=amethods: raise ValueError('backend/card method mismatch')
    return dict(schema='embodied.evidence_benchmark.unified_plan.v1',split='observed_development',
                track='fixed_candidate_no_planner',relation_protocol=str(relation.relative_to(ROOT)),
                attribute_protocol=str(attribute.relative_to(ROOT)),cases=build_cases(rp,ap),
                planned_episodes=rp['planned_episodes']+ap['expected'],
                backend_planned_episodes={'any_cookware_v0':rp['planned_episodes'],'target_knob_off_v0':ap['expected']},
                method_matrix=card['method_matrix'],stage_order=list(STAGES),
                stage_timeout_seconds=300,source_sha256=source_hashes(relation,attribute),
                limitations=['Pre-frozen development backends only; not an arbitrary case/plugin interface',
                             'Relation and attribute retain distinct contracts, actions, attack fields and guard implementations',
                             'Failed or missing stages are explicitly recorded; no automatic retry or silent replacement',
                             'No heldout, full-task, online Planner, or arbitrary-code sandbox claim'])


def verify(path):
    p=json.loads(path.read_text()); relation=checked_path(p['relation_protocol']); attribute=checked_path(p['attribute_protocol'])
    if p!=plan(relation,attribute): raise ValueError('unified plan or source hash changed')
    return p


def freeze(a):
    rp,ap=checked_path(a.relation_protocol),checked_path(a.attribute_protocol)
    p=plan(rp,ap); out=checked_path(a.out)
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700); atomic_json(out/'protocol.json',p)
    print('UNIFIED_PLAN_FROZEN',out/'protocol.json','cases',len(p['cases']),'episodes',p['planned_episodes'],flush=True)


def commands(out,p):
    py=[sys.executable,'-B']; script=lambda n:str(ROOT/'scripts'/n)
    rr,ra,re=out/'relation_run',out/'relation_audit',out/'relation_export'
    ar,aa,ae=out/'attribute_run',out/'attribute_audit',out/'attribute_export'
    ue,ua=out/'unified_export',out/'unified_audit'
    return {
      'relation_run':py+[script('benchmark_v0_manifest_runner_v1.py'),'run','--protocol',str(ROOT/p['relation_protocol']),'--out',str(rr)],
      'relation_audit':py+[script('benchmark_v0_manifest_audit_v1.py'),'--run',str(rr),'--out',str(ra)],
      'relation_export':py+[script('benchmark_v0_manifest_attempts_v1.py'),'--run',str(rr),'--audit',str(ra),'--out',str(re)],
      'attribute_run':py+[script('benchmark_v0_attribute_native_v1.py'),'run','--protocol',str(ROOT/p['attribute_protocol']),'--out',str(ar)],
      'attribute_audit':py+[script('benchmark_v0_attribute_audit_v1.py'),'--run',str(ar),'--out',str(aa)],
      'attribute_export':py+[script('benchmark_v0_attribute_export_v1.py'),'--run',str(ar),'--audit',str(aa),'--out',str(ae)],
      'unified_export':py+[script('benchmark_v0_unified_export_v1.py'),'--relation-run',str(rr),'--relation-audit',str(ra),'--relation-export',str(re),
                           '--attribute-run',str(ar),'--attribute-audit',str(aa),'--attribute-export',str(ae),'--out',str(ue)],
      'unified_audit':py+[script('benchmark_v0_unified_audit_v2.py'),'--run',str(ue),'--relation-export',str(re),'--attribute-export',str(ae),'--out',str(ua)]}


def stage_process(command,log,timeout):
    if not math.isfinite(timeout) or timeout<=0: raise ValueError('invalid stage timeout')
    fd=os.open(log,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); process=None; start=time.monotonic_ns()
    try:
        with os.fdopen(fd,'wb',buffering=0) as stream:
            process=subprocess.Popen(command,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LIBGL_ALWAYS_SOFTWARE':'1'},
                                     stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
            try:
                code=process.wait(timeout=timeout); status='EXITED_ZERO' if code==0 else 'EXITED_NONZERO'
            except subprocess.TimeoutExpired:
                stop_group(process); code=process.returncode; status='TIMEOUT'
        return dict(status=status,returncode=code,elapsed_ns=time.monotonic_ns()-start)
    except BaseException:
        if process is not None: stop_group(process)
        raise


def allowed_partial(stage,result,out):
    # Relation runner reports nonzero for a terminal run containing failures;
    # its audit and exporter can still preserve and report those assignments.
    if stage!='relation_run' or result['status']!='EXITED_NONZERO': return False
    path=out/'relation_run/summary.json'
    if not path.exists(): return False
    try: return json.loads(path.read_text()).get('status')=='COMPLETE_WITH_FAILURES'
    except (OSError,ValueError): return False


def stage_output_ok(stage,out):
    checks={'relation_run':('relation_run/summary.json',('COMPLETE','COMPLETE_WITH_FAILURES')),
            'relation_audit':('relation_audit/audit.json',('PASS_MANIFEST_SUITE_COMPOSITION_AUDIT',)),
            'attribute_run':('attribute_run/status.json',('COMPLETE','COMPLETE_WITH_FAILURES')),
            'attribute_audit':('attribute_audit/audit.json',('PASS_ATTRIBUTE_NATIVE_AUDIT',)),
            'unified_audit':('unified_audit/audit.json',('PASS_UNIFIED_EXPORT_AUDIT',))}
    if stage in checks:
        path,valid=checks[stage]
        try: return json.loads((out/path).read_text()).get('status') in valid
        except (OSError,ValueError): return False
    checks2={'relation_export':'relation_export/attempts.jsonl','attribute_export':'attribute_export/episodes.jsonl',
             'unified_export':'unified_export/episodes.jsonl'}
    return (out/checks2[stage]).is_file()


def run(a):
    protocol=checked_path(a.protocol); p=verify(protocol); out=checked_path(a.out)
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'protocol.json').write_bytes(protocol.read_bytes()); os.chmod(out/'protocol.json',0o600)
    state=dict(schema='embodied.evidence_benchmark.unified_execution.v1',status='STARTED',
               source_protocol_sha256=sha(protocol),planned_episodes=p['planned_episodes'],
               stages=[dict(stage=s,status='PLANNED') for s in STAGES],start_wall_ns=time.time_ns())
    def persist(): atomic_json(out/'status.json',state)
    persist(); old={s:signal.signal(s,terminate_handler) for s in (signal.SIGTERM,signal.SIGHUP)}
    cmd=commands(out,p); succeeded=set(); current=None
    depends={'relation_run':(), 'relation_audit':('relation_run',),'relation_export':('relation_audit',),
             'attribute_run':(),'attribute_audit':('attribute_run',),'attribute_export':('attribute_audit',),
             'unified_export':('relation_export','attribute_export'),'unified_audit':('unified_export',)}
    try:
        for current in state['stages']:
            name=current['stage']; missing=[x for x in depends[name] if x not in succeeded]
            if missing:
                current.update(status='BLOCKED_MISSING_DEPENDENCIES',missing=missing); persist(); print('STAGE_BLOCKED',name,flush=True); continue
            current.update(status='STARTED',start_wall_ns=time.time_ns()); persist(); print('STAGE_STARTED',name,flush=True)
            try:
                result=stage_process(cmd[name],out/(name+'.log'),p['stage_timeout_seconds']); current.update(result,finished_wall_ns=time.time_ns())
                if (result['status']=='EXITED_ZERO' or allowed_partial(name,result,out)) and stage_output_ok(name,out):
                    current['status']='COMPLETE_WITH_SOURCE_FAILURES' if allowed_partial(name,result,out) else 'COMPLETE'
                    succeeded.add(name)
                elif result['status']=='EXITED_ZERO': current['status']='INVALID_OR_MISSING_OUTPUT'
            except Exception as exc:
                current.update(status='SUPERVISOR_ERROR',error=repr(exc),traceback=traceback.format_exc())
            persist(); print('STAGE_STATUS',name,current['status'],flush=True)
        state['status']='COMPLETE' if len(succeeded)==len(STAGES) else 'COMPLETE_WITH_STAGE_FAILURES'
        if state['status']=='COMPLETE':
            unified=json.loads((out/'unified_export/summary.json').read_text())
            state.update(planned_episodes=unified['planned'],audited_completed=unified['audited_completed'])
            if unified['audited_completed']!=unified['planned']: state['status']='COMPLETE_WITH_INCOMPLETE_EPISODES'
    except KeyboardInterrupt as exc:
        state.update(status='INTERRUPTED',interruption=str(exc))
        if current and current['status']=='STARTED': current['status']='INTERRUPTED'
    except Exception as exc:
        state.update(status='FAILED',error=repr(exc),traceback=traceback.format_exc())
    finally:
        state['end_wall_ns']=time.time_ns(); persist()
        for s,h in old.items(): signal.signal(s,h)
    print('UNIFIED_EXECUTION_STATUS',state['status'],flush=True)
    return 0 if state['status']=='COMPLETE' else 1


def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='command',required=True)
    x=sub.add_parser('freeze'); x.add_argument('--relation-protocol',required=True); x.add_argument('--attribute-protocol',required=True); x.add_argument('--out',required=True); x.set_defaults(func=freeze)
    x=sub.add_parser('run'); x.add_argument('--protocol',required=True); x.add_argument('--out',required=True); x.set_defaults(func=run)
    a=ap.parse_args(); value=a.func(a); return value if isinstance(value,int) else 0

if __name__=='__main__': sys.exit(main())
