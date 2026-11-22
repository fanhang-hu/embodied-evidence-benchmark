"""Export aggregate task metrics from a completely audited E6 runtime track."""
from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha
from e5_validation.task_recovery_v2 import goal
from e6_validation.runtime_report import stage_report
from e6_validation.runtime_v3 import load_rows


def workspace_path(path):
    path = Path(path)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(ROOT / 'results/E6'):
        raise ValueError('E6 run and audit must be below results/E6')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--audit', required=True, help='path to audit.json')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    run, audit, out = workspace_path(args.run), workspace_path(args.audit), checked_path(args.out)
    track, _, _ = stage_report('benchmark_task_development', run, audit)
    rows = load_rows(run)
    groups = collections.defaultdict(list)
    for row in rows:
        groups[(row['family'], row['condition'], row['arm'], row['pollution_mode'], row['persistence'], row['planner_mode'])].append(row)
    summary = []
    for (family, condition, arm, mode, persistence, planner), subset in sorted(groups.items()):
        steps = [step for row in subset for step in row['steps']]
        unsafe = [step for step in steps if step['unsafe_candidate']]
        safe = [step for step in steps if not step['unsafe_candidate']]
        summary.append(dict(family=family, condition=condition, arm=arm, pollution_mode=mode,
            persistence=persistence, planner_mode=planner, episodes=len(subset),
            scenes=len({r['scene'] for r in subset}), goal_satisfied=sum(goal(r['final_truth'],r['case']) for r in subset),
            safe_task_success=sum(r['safe_task_success'] for r in subset),
            execution_violations=sum(r['execution_violation'] for r in subset),
            unsafe_candidates=len(unsafe), unsafe_allowed=sum(s['authorization']=='ALLOW' for s in unsafe),
            safe_candidates=len(safe), safe_blocked=sum(s['authorization']=='BLOCK' for s in safe),
            safe_deferred=sum(s['authorization']=='DEFER' for s in safe),
            protected_queries=sum(len(r['trusted_queries']) for r in subset),
            producer_publications=sum(len(r['publications']) for r in subset),
            native_action_failures=sum(s['executor_receipt'] is not None and not s['executor_receipt']['success'] for s in steps),
            median_pipeline_ms=statistics.median(r['pipeline_ns']/1e6 for r in subset)))
    result = dict(schema='embodied.evidence_benchmark.task_summary.v1',
        source_run=str(run.relative_to(ROOT)), source_audit=str(audit.relative_to(ROOT)),
        source_audit_sha256=sha(audit), source_records_sha256=track['records_sha256'],
        exporter_sha256=sha(Path(__file__).resolve()), planner_mode=track['planner_mode'],
        split=track['split'], episodes=track['episodes'], scene_clusters=track['scene_clusters'], groups=summary,
        limitations=['Audited complete tracks only; incomplete runs are not scored by this exporter',
          'Fixed deterministic or archived task plan is not an online planner; consult planner_mode',
          'Goal and violation labels use evaluator truth; full Unity execution is not independently replayed',
          'Protected Unity query is oracle-like and uses the same simulator',
          'Pipeline time excludes setup, producer startup and serialization; includes evaluator drift where present',
          'Cases and contracts sharing a scene are clustered; do not pool as independent scenes'])
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    path = out/'summary.json'; path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    os.chmod(path,0o600)
    print('TASK_SUMMARY',len(rows),'EPISODES',result['scene_clusters'],'SCENES')


if __name__=='__main__':
    main()
