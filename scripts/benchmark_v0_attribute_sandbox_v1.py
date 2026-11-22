"""Bubblewrap launcher and public-observation projection for V0 Guard probes."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import select
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OBJECT_FIELDS = frozenset(('objectId', 'objectType', 'position', 'parentReceptacles', 'isToggled', 'controlledObjects'))
FILES = (
    ('scripts/benchmark_v0_attribute_worker_v1.py', '/bench/scripts/benchmark_v0_attribute_worker_v1.py'),
    ('scripts/benchmark_v0_attribute_guard_v1.py', '/bench/scripts/benchmark_v0_attribute_guard_v1.py'),
    ('scripts/benchmark_v0_guard_interface.py', '/bench/scripts/benchmark_v0_guard_interface.py'),
    ('scripts/benchmark_v0_external_kitchen_guard_v2.py', '/bench/scripts/benchmark_v0_external_kitchen_guard_v2.py'),
    ('external/safe-hierarchical-embodied-ai/src/ae_rl/__init__.py', '/bench/external/safe-hierarchical-embodied-ai/src/ae_rl/__init__.py'),
    ('external/safe-hierarchical-embodied-ai/src/ae_rl/execution/__init__.py', '/bench/external/safe-hierarchical-embodied-ai/src/ae_rl/execution/__init__.py'),
    ('external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py', '/bench/external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py'),
    ('external/safe-hierarchical-embodied-ai/src/ae_rl/execution/safety.py', '/bench/external/safe-hierarchical-embodied-ai/src/ae_rl/execution/safety.py'),
)


def project(public):
    """Whitelist fields required by the current two contracts/Guard component."""
    if not isinstance(public, dict) or not isinstance(public.get('objects'), list):
        raise ValueError('Invalid public observation')
    result = []
    for obj in public['objects']:
        if not isinstance(obj, dict) or not isinstance(obj.get('objectId'), str) or not isinstance(obj.get('objectType'), str):
            raise ValueError('Object identity or type missing')
        item = {k: copy.deepcopy(v) for k, v in obj.items() if k in OBJECT_FIELDS}
        if 'position' in item:
            pos = item['position']
            if not isinstance(pos, dict) or not all(k in pos and type(pos[k]) in (int, float) for k in ('x', 'y', 'z')):
                raise ValueError('Invalid position')
            item['position'] = {k: pos[k] for k in ('x', 'y', 'z')}
        if 'controlledObjects' in item and item['controlledObjects'] is not None:
            if not isinstance(item['controlledObjects'], list) or not all(isinstance(x, str) for x in item['controlledObjects']):
                raise ValueError('Invalid controlledObjects')
        if 'parentReceptacles' in item and item['parentReceptacles'] is not None:
            if not isinstance(item['parentReceptacles'], list) or not all(isinstance(x, str) for x in item['parentReceptacles']):
                raise ValueError('Invalid parentReceptacles')
        result.append(item)
    if len({o['objectId'] for o in result}) != len(result):
        raise ValueError('Duplicate object identities')
    return {'objects': result}


def command(private_probe_path):
    cmd = ['/usr/bin/bwrap', '--unshare-user', '--unshare-pid', '--die-with-parent',
           '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
           '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
           '--dir', '/bench', '--dir', '/bench/scripts', '--dir', '/bench/external',
           '--dir', '/bench/external/safe-hierarchical-embodied-ai',
           '--dir', '/bench/external/safe-hierarchical-embodied-ai/src',
           '--dir', '/bench/external/safe-hierarchical-embodied-ai/src/ae_rl',
           '--dir', '/bench/external/safe-hierarchical-embodied-ai/src/ae_rl/execution']
    for source, dest in FILES:
        cmd += ['--ro-bind', str(ROOT / source), dest]
    cmd += ['--chdir', '/bench', '--setenv', 'PATH', '/usr/bin:/bin',
            '--', '/usr/bin/python3', '-I', '-B', '/bench/scripts/benchmark_v0_attribute_worker_v1.py', private_probe_path]
    return cmd


class GuardProcess:
    def __init__(self, private_probe_path, timeout=15):
        self.timeout = timeout
        self.proc = subprocess.Popen(command(private_probe_path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, bufsize=0, close_fds=True, env={})
        self.buffer = b''
        try:
            self.boundary = self._read()
            if not self.boundary.get('ready') or not all(self.boundary.get('probes', {}).values()):
                raise RuntimeError('Guard isolation checks failed: ' + str(self.boundary))
        except BaseException:
            self.close()
            raise

    def _read(self):
        deadline = time.monotonic() + self.timeout
        while b'\n' not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.proc.stdout], [], [], left)[0]:
                raise TimeoutError('Guard response timed out')
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                error = self.proc.stderr.read(4096).decode(errors='replace')
                raise RuntimeError('Guard exited: ' + error)
            self.buffer += chunk
            if len(self.buffer) > 16 * 1024 * 1024:
                raise ValueError('Guard response exceeds bound')
        line, self.buffer = self.buffer.split(b'\n', 1)
        return json.loads(line)

    def evaluate(self, request):
        data = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        self.proc.stdin.write(data)
        result = self._read()
        if 'error' in result:
            raise RuntimeError('Guard rejected input: ' + str(result))
        return result['result']

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        if self.proc.stdout: self.proc.stdout.close()
        if self.proc.stderr: self.proc.stderr.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
