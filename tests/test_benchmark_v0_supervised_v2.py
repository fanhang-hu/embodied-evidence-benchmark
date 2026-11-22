import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_supervised_suite_v2 import supervise, run


class SupervisorTests(unittest.TestCase):
    def test_exit_status_and_private_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            for code in (0, 7):
                path = Path(tmp) / str(code)
                r = supervise([sys.executable, '-c', f'print("child"); raise SystemExit({code})'], path, 5)
                self.assertEqual(r['status'], 'EXITED_ZERO' if code == 0 else 'FAILED')
                self.assertEqual(r['returncode'], code)
                self.assertIn('child', path.read_text())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_timeout_stops_sigterm_ignoring_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'grandchild.pid'
            childcode = ('import os,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                         'open(sys.argv[1],"w").write(str(os.getpid())); time.sleep(30)')
            parentcode = ('import subprocess,sys,time; '
                          'subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]); time.sleep(30)')
            result = supervise([sys.executable, '-c', parentcode, childcode, str(pidfile)], Path(tmp) / 'log', 0.7)
            self.assertEqual(result['status'], 'TIMEOUT')
            self.assertTrue(pidfile.exists())
            pid = int(pidfile.read_text())
            def active():
                try:
                    state = Path(f'/proc/{pid}/stat').read_text().split(') ')[1].split()[0]
                    return state != 'Z'
                except FileNotFoundError:
                    return False
            for _ in range(30):
                if not active(): break
                time.sleep(0.05)
            self.assertFalse(active(), 'descendant still running after timeout')

    def test_interruption_records_remaining_cases(self):
        protocol = ROOT / 'results/benchmark_v0/suite_protocol_20261122_01/protocol.json'
        with tempfile.TemporaryDirectory(dir=ROOT / 'results/benchmark_v0') as tmp, patch('benchmark_v0_supervised_suite_v2.supervise', side_effect=KeyboardInterrupt('test')):
            out = Path(tmp) / 'run'
            self.assertEqual(run(protocol, out, 1), 1)
            state = json.loads((out / 'status.json').read_text())
            self.assertEqual(state['status'], 'INTERRUPTED')
            self.assertEqual([c['status'] for c in state['cases']], ['INTERRUPTED', 'NOT_STARTED'])

    def test_real_sigterm_leaves_durable_interrupted_status(self):
        protocol = ROOT / 'results/benchmark_v0/suite_protocol_20261122_01/protocol.json'
        with tempfile.TemporaryDirectory(dir=ROOT / 'results/benchmark_v0') as tmp:
            out = Path(tmp) / 'run'
            cmd = [sys.executable, '-B', str(ROOT / 'scripts/benchmark_v0_supervised_suite_v2.py'),
                   '--protocol', str(protocol), '--out', str(out), '--case-timeout-seconds', '30']
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if (out / 'status.json').exists():
                        state = json.loads((out / 'status.json').read_text())
                        if state['cases'][0]['status'] == 'STARTED': break
                    time.sleep(0.02)
                else: self.fail('supervisor never started')
                os.kill(p.pid, signal.SIGTERM)
                self.assertEqual(p.wait(timeout=10), 1)
                state = json.loads((out / 'status.json').read_text())
                self.assertEqual(state['status'], 'INTERRUPTED')
                self.assertEqual(state['cases'][0]['status'], 'INTERRUPTED')
                self.assertEqual(state['cases'][1]['status'], 'NOT_STARTED')
            finally:
                if p.poll() is None:
                    p.kill(); p.wait()

    def test_invalid_timeout_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in (0, -1, float('inf'), float('nan')):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    supervise([sys.executable, '-c', 'pass'], Path(tmp) / 'log', value)


if __name__ == '__main__': unittest.main()
