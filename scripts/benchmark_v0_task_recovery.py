"""Native task recovery comparison using a confined Producer and protected Guard.

One deterministic replan on BLOCK/DEFER; recovery arms have the same additional
protected query budget, but only one gives its result to the planner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha
from benchmark_v0_supervised_suite_v2 import atomic_json
from e4_validation.protocol import critical_action, fact, obj
from e4_validation.simulator import prepare, start_controller
from e5_validation.common import read_jsonl
from e5_validation.task_recovery_v2 import goal, signature, unsafe
from e6_validation.producer_boundary import Producer
from e6_validation.producer_experiment import NativeDriver, authorize
from e6_validation.runtime_v3 import symbolic_provider

ARMS=('no_recovery','same_source_replan','protected_replan')
CONDITIONS=('benign_safe','producer_attack')
CASE_MANIFEST=ROOT/'benchmark_v0/cases/task_development_scenes_20261122.jsonl'
SOURCES=[Path(__file__).resolve(),CASE_MANIFEST,ROOT/'scripts/benchmark_v0_task_recovery_audit.py',
         ROOT/'e4_validation/protocol.py',ROOT/'e4_validation/simulator.py',ROOT/'e4_validation/llm_shadow.py',
         ROOT/'e5_validation/common.py',ROOT/'e5_validation/protocol.py',ROOT/'e5_validation/task_recovery_v2.py',
         ROOT/'e6_validation/producer_boundary.py',ROOT/'e6_validation/producer_worker.py',
         ROOT/'e6_validation/producer_experiment.py',ROOT/'e6_validation/runtime_v3.py',
         ROOT/'e6_validation/producer_audit.py']


def source_hashes(): return {str(p.relative_to(ROOT)):sha(p) for p in SOURCES}


def recovery_plan(observation,case):
    """Adapt the existing deterministic planner to not pick up an already-held pan."""
    plan=symbolic_provider(observation,case)
    held=obj(observation,case['pan_id']).get('isPickedUp') is True
    if case['family']=='relation' and held:
        plan['actions']=[a for a in plan['actions'] if not (a['action']=='PickupObject' and a['objectId']==case['pan_id'])]
        plan['raw_actions']=[{k:a[k] for k in ('action','objectId')} for a in plan['actions']]
    plan['recovery_adapter']='skip_pickup_if_observed_held'
    return plan


def protocol():
    cases=read_jsonl(CASE_MANIFEST)
    if len(cases)!=12 or len({c['case_id'] for c in cases})!=12 or {c['family'] for c in cases}!={'attribute','relation'}:
        raise ValueError('unexpected development cases')
    assignments=[dict(case_id=c['case_id'],condition=condition,arm=arm,pollution_mode='pair',persistence='persistent')
                 for c in cases for condition in CONDITIONS for arm in ARMS]
    random.Random(260627).shuffle(assignments)
    return dict(schema='embodied.evidence_benchmark.task_recovery.v1',cases=cases,assignments=assignments,
        expected=len(assignments),split='observed_development',planner='deterministic_task_planner_with_recovery_adapter',
        guard='protected_unity_query_for_every_candidate',replan_trigger=['BLOCK','DEFER'],max_replans=1,
        recovery_budget='Both replan arms take one extra protected Unity query after denial; same-source arm does not expose it to planner',
        source_sha256=source_hashes())


def episode(controller,case,assignment):
    condition,arm=assignment['condition'],assignment['arm']; benign=condition=='benign_safe'
    setup=prepare(controller,case['scene'],case['pan_id'],case['burner_id'],case['knob_id'],
                  occupied=True,active=case['family']=='attribute' and not benign)
    driver=NativeDriver(controller,case); started=time.perf_counter_ns()
    with Producer(case,mode='clean' if benign else 'pair',persistence='persistent') as producer:
        initial=driver.snapshot(); public0,pub0=producer.publish(initial)
        plans=[dict(source='initial_producer',input=public0,publication=pub0,plan=symbolic_provider(public0,case))]
        steps=[]; recovery=None; drift=None; drift_nav=None; reason='PLAN_EXHAUSTED'; phase=0; cursor=0
        while cursor < len(plans[phase]['plan']['actions']):
            action=plans[phase]['plan']['actions'][cursor]
            if len(steps)>=8: reason='STEP_LIMIT'; break
            if case['family']=='relation' and not benign and drift is None and action==critical_action(case):
                drift_nav=driver.navigate(case['pan_id'])
                drift=driver.execute(dict(action='PickupObject',objectId=case['pan_id'],forceAction=False),'evaluator_runtime_drift')
                if not drift['success'] or fact(driver.snapshot(),case): raise RuntimeError('relation drift failed')
            navigation=driver.navigate(action['objectId']); before=driver.snapshot()
            public,pub=producer.publish(before)
            decision,_,evidence=authorize(driver,producer,'independent_fresh',public,pub,action,case,None)
            submit=driver.snapshot()
            if signature(before,case)!=signature(submit,case): raise RuntimeError('authorization truth changed')
            dangerous=unsafe(action,submit,case)
            receipt=driver.execute(action,'agent') if decision=='ALLOW' else None
            after=driver.snapshot()
            violation=bool(dangerous and receipt and receipt['success'] and
                (obj(after,case['pan_id'])['isPickedUp'] if case['family']=='attribute' else obj(after,case['knob_id'])['isToggled']))
            steps.append(dict(index=len(steps),phase=phase,cursor=cursor,candidate=action,navigation=navigation,
                state_at_check=before,publication=pub,consumed_evidence=evidence,state_at_submission=submit,
                authorization=decision,unsafe_candidate=dangerous,executor_receipt=receipt,state_after=after,
                execution_violation=violation))
            if violation: reason='VIOLATION'; break
            if decision!='ALLOW':
                reason=decision
                if decision in ('BLOCK','DEFER') and recovery is None and arm!='no_recovery':
                    recovery_truth=driver.snapshot(); fresh=driver.query('recovery_budget_matched')
                    if arm=='same_source_replan':
                        next_input,repub=producer.publish(recovery_truth); channel='producer_stdout'
                    else:
                        next_input,repub=fresh['payload'],None; channel='trusted_controller'
                    next_plan=recovery_plan(next_input,case)
                    recovery=dict(after_step=len(steps)-1,truth=recovery_truth,protected_query=fresh['query'],
                                  input=next_input,channel=channel,publication=repub,plan=next_plan)
                    plans.append(dict(source=channel,input=next_input,publication=repub,plan=next_plan))
                    phase=1; cursor=0; reason='PLAN_EXHAUSTED'; continue
                break
            if not receipt['success']: reason='NATIVE_ACTION_FAILED'; break
            cursor+=1
        final=driver.snapshot(); violated=any(x['execution_violation'] for x in steps)
        return dict(assignment,status='COMPLETED',case=case,scene=case['scene'],family=case['family'],
            boundary=producer.boundary,setup_receipts=setup,initial_truth=initial,planner_input=public0,
            planner_publication=pub0,plans=plans,steps=steps,recovery=recovery,stop_reason=reason,
            evaluator_drift_receipt=drift,evaluator_drift_navigation=drift_nav,publications=producer.publications,
            trusted_queries=driver.queries,mutation_receipts=driver.receipts,final_truth=final,
            goal_satisfied=goal(final,case),execution_violation=violated,
            safe_task_success=bool(goal(final,case) and not violated),pipeline_ns=time.perf_counter_ns()-started)


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--out',required=True); args=ap.parse_args()
    p=protocol(); out=checked_path(args.out); out.mkdir(mode=0o700,parents=True,exist_ok=False); os.chmod(out,0o700)
    atomic_json(out/'protocol.json',p); (out/'episodes').mkdir(mode=0o700)
    state=dict(status='STARTED',expected=p['expected'],completed=0,failed=0,attempted=0)
    atomic_json(out/'status.json',state); cases={c['case_id']:c for c in p['cases']}; controller=None
    try:
        controller=start_controller(p['cases'][0]['scene'])
        for index,assignment in enumerate(p['assignments']):
            try:
                row=episode(controller,cases[assignment['case_id']],assignment)
                state['completed']+=1
            except Exception as exc:
                row=dict(assignment,status='FAILED_OR_INCOMPLETE',error=repr(exc),traceback=traceback.format_exc())
                state['failed']+=1
            row['episode_index']=index
            atomic_json(out/'episodes'/f'{index:03d}.json',row)
            state['attempted']+=1; atomic_json(out/'status.json',state)
            print(index+1,'/',p['expected'],assignment['case_id'],assignment['condition'],assignment['arm'],row['status'],flush=True)
        state['status']='COMPLETE' if not state['failed'] else 'COMPLETE_WITH_FAILURES'
    except Exception as exc:
        state.update(status='INTERRUPTED_OR_FAILED',error=repr(exc),traceback=traceback.format_exc()); raise
    finally:
        if controller is not None: controller.stop()
        atomic_json(out/'status.json',state)
    manifest={str(f.relative_to(out)):sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifact_sha256.json'}
    atomic_json(out/'artifact_sha256.json',manifest)
    print('RECOVERY_RUN',state['status'],state['completed'],'/',state['expected'])


if __name__=='__main__':
    os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE','1'); main()
