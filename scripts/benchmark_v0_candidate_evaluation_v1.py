"""Frozen exploratory candidate evaluation with case injection and per-case audits.

Case injection adapts the old pilot and its audit to an external case manifest.
It is not a formal held-out evaluation or the official external controller.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import random
import signal
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import ARMS, CONDITIONS, checked_path, hashes, sha
from benchmark_v0_supervised_suite_v2 import atomic_json, terminate_handler
from benchmark_v0_episode_supervisor_v1 import monitor
from benchmark_v0_attempts_v2 import audited_case

CANDIDATES = ROOT / 'results/benchmark_v0/candidate_scene_manifest_20261122_01/candidates.jsonl'
MANIFEST = CANDIDATES.with_name('manifest.json')
SOURCE = Path(__file__).resolve()
EXTRA = [SOURCE, CANDIDATES, MANIFEST, ROOT/'scripts/benchmark_v0_episode_supervisor_v1.py',
         ROOT/'scripts/benchmark_v0_supervised_suite_v2.py', ROOT/'scripts/benchmark_v0_attempts_v2.py',
         ROOT/'results/benchmark_v0/candidate_scene_discovery_20261122_01/protocol.json',
         ROOT/'results/benchmark_v0/candidate_scene_discovery_20261122_01/status.json']
SEED = 260626


def source_hashes():
    h = hashes()
    h.update({str(p.relative_to(ROOT)): sha(p) for p in EXTRA})
    return h


def frozen_cases():
    meta = json.loads(MANIFEST.read_text())
    if meta['output_sha256'] != sha(CANDIDATES): raise ValueError('candidate manifest hash')
    records = [json.loads(line) for line in CANDIDATES.read_text().splitlines() if line.strip()]
    if len(records) != meta['candidates'] or len(records) != 4: raise ValueError('candidate count')
    fields = ('case_id', 'scene', 'family', 'pan_id', 'burner_id', 'knob_id')
    cases = []
    for record in records:
        if record['status'] != 'PROVISIONAL_METADATA_ELIGIBLE' or record['split'] != 'unassigned_candidate_not_heldout':
            raise ValueError('candidate not eligible')
        if record['source_protocol_sha256'] != meta['source_protocol_sha256'] or record['source_discovery_status_sha256'] != meta['source_discovery_status_sha256']:
            raise ValueError('candidate provenance')
        c = {k: record[k] for k in fields}
        if c['family'] != 'relation': raise ValueError('unsupported family')
        cases.append(c)
    if len({c['case_id'] for c in cases}) != len(cases) or [c['scene'] for c in cases] != [f'FloorPlan{i}' for i in (11,12,13,14)]:
        raise ValueError('case IDs or ordering')
    return cases


def protocol_check(path):
    p = json.loads(path.read_text())
    if p.get('schema') != 'embodied.evidence_benchmark.candidate_evaluation.v1' or p.get('source_sha256') != source_hashes():
        raise ValueError('frozen protocol sources changed')
    if p['cases'] != frozen_cases() or p['guards'] != list(ARMS) or p['conditions'] != list(CONDITIONS) or p['seed'] != SEED:
        raise ValueError('frozen experiment differs')
    if p['planned_episodes'] != len(p['cases'])*len(ARMS)*len(CONDITIONS): raise ValueError('count mismatch')
    return p


def freeze(args):
    cases = frozen_cases()
    p = dict(schema='embodied.evidence_benchmark.candidate_evaluation.v1', split='exploratory_candidate_not_heldout',
             cases=cases, conditions=list(CONDITIONS), guards=list(ARMS), seed=SEED,
             planned_episodes=len(cases)*len(CONDITIONS)*len(ARMS), repeats_per_case_condition_guard=1,
             contract='any_cookware_v0', track='fixed_candidate_no_planner',
             producer_attack='persistent pair: selected cookware parentReceptacles and position',
             episode_timeout_from_observed_start_seconds=60, case_timeout_seconds=180,
             failure_rule='Record and retain each failure, proceed to next preselected case, no replacements or retries',
             eligibility_rule='Use all four preselected metadata candidates; prepare or truth setup failures remain failures',
             audit_rule='Legacy pilot and auditor receive exact frozen candidate record through explicitly patched catalogue reader; audit replay is independent of pilot outcome but shares adapter code and source',
             metric_rule='Report planned assignments, per-case completion/audit, and audited case metrics; incomplete cases not counted as safe',
             limitations=['Historical independence unverified; not formal heldout', 'One repetition; fixed candidate, no online Planner',
                          'Any-cookware minimal condition, not full hazard policy', 'Oracle-like protected Unity query',
                          'Legacy runner and auditor adapted with shared case reader; source provenance bound here'],
             source_sha256=source_hashes())
    out=checked_path(args.out); out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    atomic_json(out/'protocol.json',p); print('FROZEN_EXPLORATORY_EVALUATION', out/'protocol.json', flush=True)


def child(args):
    p=protocol_check(checked_path(args.protocol))
    matches=[x for x in p['cases'] if x['case_id']==args.case]
    if len(matches)!=1: raise ValueError('unknown case')
    case=matches[0]
    import benchmark_v0_external_native as pilot
    import benchmark_v0_external_native_audit as audit
    # Both components must evaluate the same pre-registered candidate rather
    # than selecting from their old hard-coded E4 development catalogue.
    pilot.read_jsonl=lambda ignored: [case]
    pilot.CASE_ID=case['case_id']; pilot.OUT=checked_path(args.run)
    pilot.main()
    audit.read_jsonl=lambda ignored: [case]
    audit.RUN=pilot.OUT; audit.OUT=checked_path(args.audit)
    audit.main()


def aggregate(cases, out):
    groups=[]
    for condition in CONDITIONS:
        for arm in ARMS:
            selected=[]
            for c in cases:
                if c['status']!='AUDITED': continue
                s=json.loads((out/('run_'+c['case_id'])/'summary.json').read_text())
                rows=[g for g in s['groups'] if g['condition']==condition and g['arm']==arm]
                if len(rows)!=1: raise ValueError('case metrics mismatch')
                selected.extend(rows)
            sums={key:sum(r[key] for r in selected) for key in ('unsafe_candidates','unsafe_allowed','actual_violations',
                  'safe_candidates','safe_candidate_executed','safe_deferred','protected_queries')}
            groups.append(dict(condition=condition,guard=arm,planned=len(cases),audited_completed=len(selected),**sums))
    return groups


def run(args):
    protocol_path=checked_path(args.protocol); p=protocol_check(protocol_path); out=checked_path(args.out)
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    (out/'protocol.json').write_bytes(protocol_path.read_bytes()); os.chmod(out/'protocol.json',0o600)
    cases=[]
    for c in p['cases']:
        assignments=[dict(condition=condition,guard=arm) for condition in CONDITIONS for arm in ARMS]
        random.Random(SEED).shuffle(assignments)
        episodes=[dict(assignment_id=f"{c['case_id']}:{i:02d}",case_id=c['case_id'],scene=c['scene'],index=i,
                       status='PLANNED',audit_status='NOT_YET_VERIFIED',**a) for i,a in enumerate(assignments)]
        cases.append(dict(case_id=c['case_id'],scene=c['scene'],status='PLANNED',episodes=episodes))
    state=dict(schema='embodied.evidence_benchmark.candidate_run.v1',status='STARTED',
               source_protocol_sha256=sha(protocol_path),planned_episodes=p['planned_episodes'],
               start_wall_ns=time.time_ns(),cases=cases)
    def persist(): atomic_json(out/'journal.json',state)
    persist(); previous={s:signal.signal(s,terminate_handler) for s in (signal.SIGTERM,signal.SIGHUP)}
    current=None
    try:
        for current in cases:
            cid=current['case_id']; case_dir=out/('run_'+cid); audit_dir=out/('audit_'+cid)
            current.update(status='STARTED',start_wall_ns=time.time_ns()); persist()
            print('CANDIDATE_CASE_STARTED',cid,flush=True)
            command=[sys.executable,'-B',str(SOURCE),'child','--protocol',str(protocol_path),'--case',cid,
                     '--run',str(case_dir),'--audit',str(audit_dir)]
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LIBGL_ALWAYS_SOFTWARE':'1'}
            try:
                result=monitor(command,case_dir,current['episodes'],out/('case_'+cid+'.log'),
                               p['episode_timeout_from_observed_start_seconds'],p['case_timeout_seconds'],persist,env=env)
                current.update(result,finished_wall_ns=time.time_ns())
                if result['status']=='EXITED_ZERO':
                    if not audited_case(out,cid): current['status']='AUDIT_MISSING'
                    elif any(r['status']!='COMPLETED_RECORDED' for r in current['episodes']): current['status']='JOURNAL_MISMATCH'
                    else:
                        current.update(status='AUDITED',audit_sha256=sha(audit_dir/'audit.json'),
                                       manifest_sha256=sha(case_dir/'artifact_sha256.json'))
                        for r in current['episodes']: r['audit_status']='PASS'
            except Exception as exc:
                current.update(status='SUPERVISOR_ERROR',error=repr(exc),traceback=traceback.format_exc())
            for row in current['episodes']:
                if row['status'] in ('PLANNED','RUNNING_OBSERVED'):
                    row.update(status='UNKNOWN',reason='no trustworthy terminal record for launched case')
            persist(); print('CANDIDATE_CASE_STATUS',cid,current['status'],flush=True)
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
        for s,h in previous.items(): signal.signal(s,h)
    try:
        summary=dict(schema='embodied.evidence_benchmark.candidate_summary.v1',status=state['status'],
                     source_protocol_sha256=sha(protocol_path),journal_sha256=sha(out/'journal.json'),
                     planned_cases=len(cases),audited_cases=sum(c['status']=='AUDITED' for c in cases),
                     planned_episodes=p['planned_episodes'],cases=[dict(case_id=c['case_id'],scene=c['scene'],status=c['status']) for c in cases],
                     groups=aggregate(cases,out),limitations=p['limitations'])
        atomic_json(out/'summary.json',summary)
    except Exception as exc:
        print('SUMMARY_FAILED',repr(exc),flush=True); return 1
    print('CANDIDATE_EVALUATION_STATUS',state['status'],flush=True)
    return 0 if state['status']=='COMPLETE' else 1


def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('freeze'); p.add_argument('--out',required=True); p.set_defaults(func=freeze)
    p=sub.add_parser('run'); p.add_argument('--protocol',required=True); p.add_argument('--out',required=True); p.set_defaults(func=run)
    p=sub.add_parser('child'); p.add_argument('--protocol',required=True); p.add_argument('--case',required=True); p.add_argument('--run',required=True); p.add_argument('--audit',required=True); p.set_defaults(func=child)
    a=ap.parse_args(); result=a.func(a); return result if isinstance(result,int) else 0

if __name__=='__main__': sys.exit(main())
