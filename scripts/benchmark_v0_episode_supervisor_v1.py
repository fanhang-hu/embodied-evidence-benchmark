"""Observe legacy episode progress, enforce observed-start deadlines and retain a journal.

Observed start is after polling the legacy status file; it is not exact start.
Completed records remain provisional until the separate case audit passes.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import ARMS, CONDITIONS, checked_path, sha, verify_protocol
from benchmark_v0_supervised_suite_v2 import atomic_json, stop_group, terminate_handler
from benchmark_v0_attempts_v2 import audited_case


def read_progress(path, count):
    try:
        state = json.loads(path.read_text())
        a, c = state['attempted'], state['completed']
        if type(a) is not int or type(c) is not int or not (0 <= c <= a <= count) or a - c > 1:
            return None
        return (a, c)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def observe(case_dir, entries, now_ns):
    """Update journal from complete episode records and valid status observations."""
    changed = False
    for i, row in enumerate(entries):
        path = case_dir / 'private' / f'{i:02d}_episode.json'
        if not path.is_file() or row['status'] in ('COMPLETED_RECORDED', 'INCOMPLETE_RECORDED'): continue
        try: source = json.loads(path.read_text())
        except (OSError, ValueError): continue
        if (source.get('index') != i or source.get('case_id') != row['case_id'] or
            source.get('condition') != row['condition'] or source.get('arm') != row['guard']):
            raise ValueError('episode file does not match frozen assignment')
        status = source.get('status')
        if status in ('COMPLETED', 'FAILED_OR_INCOMPLETE'):
            row.update(status='COMPLETED_RECORDED' if status == 'COMPLETED' else 'INCOMPLETE_RECORDED',
                       record_observed_monotonic_ns=now_ns, source_episode_sha256=sha(path),
                       audit_status='NOT_YET_VERIFIED')
            changed = True
    progress = read_progress(case_dir / 'status.json', len(entries))
    if progress is not None:
        attempted, completed = progress
        if attempted > completed:
            row = entries[attempted - 1]
            if row['status'] == 'PLANNED':
                row.update(status='RUNNING_OBSERVED', start_observed_monotonic_ns=now_ns)
                changed = True
    return changed, progress


def monitor(command, case_dir, entries, log_path, episode_timeout, case_timeout, persist,
            env=None, poll_seconds=0.05):
    if any(not math.isfinite(x) or x <= 0 for x in (episode_timeout, case_timeout, poll_seconds)):
        raise ValueError('timeouts and polling interval must be positive finite values')
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    start = time.monotonic_ns(); proc = None; timeout_index = None
    try:
        with os.fdopen(fd, 'wb', buffering=0) as stream:
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True, close_fds=True)
            while True:
                now = time.monotonic_ns()
                changed, progress = observe(case_dir, entries, now)
                if changed: persist()
                code = proc.poll()
                if code is not None:
                    return dict(status='EXITED_ZERO' if code == 0 else 'FAILED', returncode=code,
                                elapsed_ns=time.monotonic_ns() - start)
                if progress is not None and progress[0] > progress[1]:
                    idx = progress[0] - 1; row = entries[idx]
                    observed = row.get('start_observed_monotonic_ns')
                    if row['status'] == 'RUNNING_OBSERVED' and observed is not None and (now - observed) >= episode_timeout * 1e9:
                        timeout_index = idx
                        stop_group(proc)
                        changed, final = observe(case_dir, entries, time.monotonic_ns())
                        row = entries[idx]
                        if final == (idx + 1, idx) and row['status'] == 'RUNNING_OBSERVED':
                            row.update(status='TIMEOUT_OBSERVED', timeout_observed_monotonic_ns=time.monotonic_ns(),
                                       reason='deadline after observed start; final progress still points at this episode')
                        else:
                            timeout_index = None
                        persist()
                        return dict(status='EPISODE_TIMEOUT', returncode=proc.returncode, timeout_index=timeout_index,
                                    elapsed_ns=time.monotonic_ns() - start)
                if now - start >= case_timeout * 1e9:
                    stop_group(proc)
                    observe(case_dir, entries, time.monotonic_ns()); persist()
                    return dict(status='CASE_TIMEOUT', returncode=proc.returncode, elapsed_ns=time.monotonic_ns() - start)
                time.sleep(poll_seconds)
    except BaseException:
        if proc is not None:
            stop_group(proc)
            observe(case_dir, entries, time.monotonic_ns()); persist()
        raise


def run(protocol_path, out, episode_timeout, case_timeout):
    protocol = verify_protocol(protocol_path)
    if any(not math.isfinite(x) or x <= 0 for x in (episode_timeout, case_timeout)):
        raise ValueError('timeouts must be positive and finite')
    out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    (out / 'protocol.json').write_bytes(protocol_path.read_bytes()); os.chmod(out / 'protocol.json', 0o600)
    cases = []
    for c in protocol['cases']:
        assignments = [dict(condition=cond, guard=arm) for cond in CONDITIONS for arm in ARMS]
        random.Random(protocol['pilot_seed']).shuffle(assignments)
        entries = [dict(assignment_id=f"{c['case_id']}:{i:02d}", case_id=c['case_id'], scene=c['scene'],
                        index=i, status='PLANNED', audit_status='NOT_YET_VERIFIED', **assignment)
                   for i, assignment in enumerate(assignments)]
        cases.append(dict(case_id=c['case_id'], scene=c['scene'], status='PLANNED', episodes=entries))
    state = dict(schema='embodied.evidence_benchmark.episode_observation.v1', status='STARTED',
                 expected=protocol['expected_episodes'], source_protocol_sha256=sha(protocol_path),
                 observer_sha256=sha(Path(__file__).resolve()),
                 source_supervisor_sha256=sha(ROOT / 'scripts/benchmark_v0_supervised_suite_v2.py'),
                 episode_timeout_seconds_from_observed_start=episode_timeout, case_timeout_seconds=case_timeout,
                 polling_seconds=0.05, started_wall_time_ns=time.time_ns(), cases=cases)
    def persist(): atomic_json(out / 'journal.json', state)
    persist()
    previous = {s: signal.signal(s, terminate_handler) for s in (signal.SIGTERM, signal.SIGHUP)}
    current = None
    try:
        for current in cases:
            cid = current['case_id']; case_dir = out / ('run_' + cid); audit_dir = out / ('audit_' + cid)
            current.update(status='STARTED', started_wall_time_ns=time.time_ns()); persist()
            print('CASE_STARTED', cid, flush=True)
            command = [sys.executable, '-B', str(ROOT / 'scripts/benchmark_v0_suite_v1.py'), 'child', '--case', cid,
                       '--run', str(case_dir), '--audit', str(audit_dir)]
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'LIBGL_ALWAYS_SOFTWARE': '1'}
            outcome = monitor(command, case_dir, current['episodes'], out / ('case_' + cid + '.log'),
                              episode_timeout, case_timeout, persist, env=env)
            current.update(outcome, finished_wall_time_ns=time.time_ns())
            if outcome['status'] != 'EXITED_ZERO':
                state['status'] = outcome['status']; break
            if not audited_case(out, cid):
                current['status'] = state['status'] = 'AUDIT_MISSING'; break
            if any(e['status'] != 'COMPLETED_RECORDED' for e in current['episodes']):
                raise ValueError('passing case audit without complete episode records')
            current.update(status='AUDITED', audit_sha256=sha(audit_dir / 'audit.json'),
                           manifest_sha256=sha(case_dir / 'artifact_sha256.json'))
            for row in current['episodes']: row['audit_status'] = 'PASS'
            persist(); print('CASE_AUDITED', cid, flush=True)
        else: state['status'] = 'COMPLETE'
    except KeyboardInterrupt as exc:
        state.update(status='INTERRUPTED', interruption=str(exc))
        if current is not None and current['status'] == 'STARTED': current['status'] = 'INTERRUPTED'
    except Exception as exc:
        state.update(status='FAILED', error=repr(exc), traceback=traceback.format_exc())
        if current is not None and current['status'] == 'STARTED': current['status'] = 'FAILED'
    finally:
        # A launched case without a terminal episode record cannot prove that
        # unobserved episodes were never started.
        for case in cases:
            if case['status'] != 'PLANNED':
                for row in case['episodes']:
                    if row['status'] in ('PLANNED', 'RUNNING_OBSERVED'):
                        row['status'] = 'UNKNOWN'
                        row['reason'] = 'no trustworthy terminal episode record'
        state['finished_wall_time_ns'] = time.time_ns(); persist()
        for sig, handler in previous.items(): signal.signal(sig, handler)
    print('EPISODE_SUPERVISOR_STATUS', state['status'], flush=True)
    return 0 if state['status'] == 'COMPLETE' else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--protocol', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--episode-timeout-seconds', type=float, default=60)
    ap.add_argument('--case-timeout-seconds', type=float, default=300)
    args = ap.parse_args()
    return run(checked_path(args.protocol), checked_path(args.out), args.episode_timeout_seconds, args.case_timeout_seconds)

if __name__ == '__main__': sys.exit(main())
