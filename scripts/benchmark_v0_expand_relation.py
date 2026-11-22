"""Build and evaluate relation cases from a list of scenes in one command.

Selection uses only setup feasibility. All attempted setups remain in the
journal; the existing manifest runner performs and audits the actual matrix.
The resulting cases are development cases, never an implicit held-out split.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_candidate_scenes_v1 import candidates
from benchmark_v0_setup_search_v1 import attempt
from benchmark_v0_suite_v1 import checked_path, sha
from benchmark_v0_supervised_suite_v2 import atomic_json
from e4_validation.simulator import objects, start_controller


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scenes', nargs='+', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-pairs', type=int, default=4)
    a = ap.parse_args()
    if not 1 <= a.max_pairs <= 20 or len(set(a.scenes)) != len(a.scenes):
        ap.error('scenes must be unique and max-pairs must be 1..20')
    if any(not re.fullmatch(r'FloorPlan[0-9]+', s) for s in a.scenes):
        ap.error('invalid scene name')
    out = checked_path(a.out)
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    sources = [Path(__file__).resolve(), ROOT/'scripts/benchmark_v0_setup_search_v1.py',
               ROOT/'scripts/benchmark_v0_candidate_scenes_v1.py', ROOT/'e4_validation/simulator.py',
               ROOT/'e6_validation/producer_experiment.py']
    state = dict(schema='embodied.evidence_benchmark.relation_expansion.v1', status='STARTED',
                 scenes_requested=a.scenes, max_pairs=a.max_pairs, started_ns=time.time_ns(),
                 selection='first Pan (else Pot) by ID; first feasible off-knob/burner pair by ID',
                 selection_uses_attack_or_guard_outcomes=False, split='observed_development',
                 source_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources},
                 limitations=['Development cases, not an independent held-out set',
                              'Setup trial truth snapshots hashed but not retained by setup helper',
                              'Protected query is an oracle-like channel to the same simulator',
                              'Fixed candidate, no online planner or complete task'])
    state['scenes'] = [dict(scene=s, status='NOT_STARTED', attempts=[]) for s in a.scenes]
    def persist(): atomic_json(out/'selection.json', state)
    persist()
    controller = None
    selected = []
    try:
        for row in state['scenes']:
            scene = row['scene']; row['status'] = 'STARTED'; persist()
            try:
                if controller is None:
                    controller = start_controller(scene)
                else:
                    controller.reset(scene=scene)
                if not controller.last_event.metadata.get('lastActionSuccess'):
                    raise RuntimeError('scene reset failed')
                cookware, pairs = candidates(objects(controller))
                row['eligible_cookware'] = [o['objectId'] for o in cookware]
                row['eligible_pairs'] = [dict(knob_id=k, burner_id=b) for k,b in pairs]
                persist()
                if not cookware or not pairs:
                    row['status'] = 'NO_ELIGIBLE_OBJECTS'; persist(); continue
                for knob, burner in pairs[:a.max_pairs]:
                    case = dict(scene=scene, family='relation', pan_id=cookware[0]['objectId'],
                                knob_id=knob, burner_id=burner)
                    record = dict(case=case, status='STARTED', start_wall_ns=time.time_ns())
                    row['attempts'].append(record); persist()
                    try:
                        attempt(controller, case, record, persist)
                    except Exception as exc:
                        record.update(status='SETUP_INFEASIBLE', error=repr(exc), traceback=traceback.format_exc())
                        persist(); continue
                    record['status'] = 'FEASIBLE'
                    selected_case = dict(case_id='expansion_relation_'+scene+'_01', split='observed_development', **case)
                    selected.append(selected_case)
                    row.update(status='FEASIBLE', selected=selected_case); persist(); break
                else:
                    row['status'] = 'NO_FEASIBLE_PAIR'
                persist()
                print('SCENE', scene, row['status'], 'attempts', len(row['attempts']), flush=True)
            except Exception as exc:
                row.update(status='SCENE_ERROR', error=repr(exc), traceback=traceback.format_exc()); persist()
                print('SCENE', scene, 'SCENE_ERROR', repr(exc), flush=True)
                if controller is None:
                    state['status'] = 'CONTROLLER_START_FAILED'; break
    finally:
        if controller is not None:
            controller.stop()
        state['selection_finished_ns'] = time.time_ns(); persist()
    if not selected:
        if state['status'] != 'CONTROLLER_START_FAILED': state['status'] = 'NO_FEASIBLE_CASES'
        persist(); print('EXPANSION', state['status'], flush=True); return 1
    manifest = out/'cases.jsonl'
    manifest.write_text(''.join(json.dumps(c, ensure_ascii=False)+'\n' for c in selected))
    os.chmod(manifest, 0o600)
    state.update(status='EVALUATING', selected_cases=len(selected), case_manifest_sha256=sha(manifest)); persist()
    runner = ROOT/'scripts/benchmark_v0_manifest_runner_v1.py'
    steps = [
        [str(runner), 'freeze', '--cases', str(manifest), '--out', str(out/'protocol')],
        [str(runner), 'run', '--protocol', str(out/'protocol/protocol.json'), '--out', str(out/'run')],
        [str(ROOT/'scripts/benchmark_v0_manifest_audit_v1.py'), '--run', str(out/'run'), '--out', str(out/'audit')],
        [str(ROOT/'scripts/benchmark_v0_manifest_attempts_v1.py'), '--run', str(out/'run'), '--audit', str(out/'audit'), '--out', str(out/'attempts')],
    ]
    state['steps'] = []
    for cmd in steps:
        result = subprocess.run([sys.executable, '-B', *cmd], cwd=ROOT)
        state['steps'].append(dict(script=Path(cmd[0]).name, returncode=result.returncode)); persist()
        # The runner can return 1 for completed-with-failures; audit/export must still run.
        if result.returncode and not (cmd[0] == str(runner) and cmd[1] == 'run' and (out/'run/summary.json').exists()):
            state['status'] = 'PIPELINE_FAILED'; persist(); return 1
    state['status'] = 'FINISHED'; state['finished_ns'] = time.time_ns(); persist()
    print('EXPANSION FINISHED', len(selected), 'cases', flush=True)
    return 0


if __name__ == '__main__':
    os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
    sys.exit(main())
