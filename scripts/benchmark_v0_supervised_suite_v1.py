"""Supervise frozen V0 case processes; retain case-level timeout and interruption evidence.

This wrapper does not change the legacy episode runner or infer individual
outcomes from a case-level timeout. It does not auto-resume unfinished runs.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha, verify_protocol
from benchmark_v0_attempts_v2 import audited_case


def atomic_json(path, value):
    temp = path.with_name('.' + path.name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def stop_group(proc, grace_seconds=2.0):
    # The child is a new session leader, so no unrelated process is signalled.
    try: os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    try: proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        proc.wait()


def supervise(command, log_path, timeout_seconds, env=None):
    """Run one child and return case-level outcome; KeyboardInterrupt propagates."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError('timeout must be a positive finite number')
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    started = time.monotonic_ns()
    proc = None
    try:
        with os.fdopen(fd, 'wb', buffering=0) as stream:
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True, close_fds=True)
            try:
                code = proc.wait(timeout=timeout_seconds)
                status = 'EXITED_ZERO' if code == 0 else 'FAILED'
            except subprocess.TimeoutExpired:
                stop_group(proc)
                code, status = proc.returncode, 'TIMEOUT'
        return dict(status=status, returncode=code, elapsed_ns=time.monotonic_ns() - started)
    except BaseException:
        if proc is not None:
            stop_group(proc)
        raise


def terminate_handler(signum, frame):
    raise KeyboardInterrupt('received signal ' + str(signum))


def run(protocol_path, out, timeout):
    protocol = verify_protocol(protocol_path)
    if not math.isfinite(timeout) or timeout <= 0: raise ValueError('timeout must be positive and finite')
    out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    (out / 'protocol.json').write_bytes(protocol_path.read_bytes()); os.chmod(out / 'protocol.json', 0o600)
    state = dict(schema='embodied.evidence_benchmark.supervised_suite.v1', status='STARTED',
                 expected=protocol['expected_episodes'], completed_audited_cases=0,
                 source_protocol_sha256=sha(protocol_path), supervisor_sha256=sha(Path(__file__).resolve()),
                 timeout_seconds_per_case=timeout, started_wall_time_ns=time.time_ns(),
                 cases=[dict(case_id=c['case_id'], scene=c['scene'], status='NOT_STARTED') for c in protocol['cases']])
    atomic_json(out / 'status.json', state)
    previous = {s: signal.signal(s, terminate_handler) for s in (signal.SIGTERM, signal.SIGHUP)}
    current = None
    try:
        for current in state['cases']:
            cid = current['case_id']
            case_run, case_audit = out / ('run_' + cid), out / ('audit_' + cid)
            log = out / ('case_' + cid + '.log')
            current.update(status='STARTED', started_wall_time_ns=time.time_ns(), log=str(log.relative_to(ROOT)))
            atomic_json(out / 'status.json', state)
            print('CASE_STARTED', cid, flush=True)
            command = [sys.executable, '-B', str(ROOT / 'scripts/benchmark_v0_suite_v1.py'), 'child', '--case', cid,
                       '--run', str(case_run), '--audit', str(case_audit)]
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'LIBGL_ALWAYS_SOFTWARE': '1'}
            result = supervise(command, log, timeout, env=env)
            current.update(result, finished_wall_time_ns=time.time_ns())
            if result['status'] == 'EXITED_ZERO':
                if not audited_case(out, cid):
                    current['status'] = 'AUDIT_MISSING'
                    raise RuntimeError('child exited without passing case audit: ' + cid)
                current.update(status='AUDITED', audit_sha256=sha(case_audit / 'audit.json'),
                               manifest_sha256=sha(case_run / 'artifact_sha256.json'))
                state['completed_audited_cases'] += 1
            else:
                state['status'] = result['status']
                break
            atomic_json(out / 'status.json', state)
            print('CASE_AUDITED', cid, flush=True)
        else:
            state['status'] = 'COMPLETE'
    except KeyboardInterrupt as exc:
        state.update(status='INTERRUPTED', interruption=str(exc))
        if current is not None and current['status'] == 'STARTED':
            current.update(status='INTERRUPTED', finished_wall_time_ns=time.time_ns())
    except Exception as exc:
        state.update(status='FAILED', error=repr(exc), traceback=traceback.format_exc())
        if current is not None and current['status'] == 'STARTED': current['status'] = 'FAILED'
    finally:
        state['finished_wall_time_ns'] = time.time_ns()
        atomic_json(out / 'status.json', state)
        for sig, handler in previous.items(): signal.signal(sig, handler)
    print('SUPERVISOR_STATUS', state['status'], flush=True)
    return 0 if state['status'] == 'COMPLETE' else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--protocol', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--case-timeout-seconds', type=float, default=300)
    args = ap.parse_args()
    return run(checked_path(args.protocol), checked_path(args.out), args.case_timeout_seconds)

if __name__ == '__main__': sys.exit(main())
