"""Trusted bootstrap inside bwrap; restrict syscalls before importing Guard.

Filesystem isolation is provided by the launcher, not this worker. The filter
is defense in depth and is not a claim of a formally secure arbitrary-code VM.
"""
from __future__ import annotations

import ctypes
import errno
import json
import os
import socket
import sys


def filter_syscalls():
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x7fff0000)  # default ALLOW; deny listed capabilities
    if not ctx:
        raise RuntimeError('seccomp_init failed')
    deny = 0x00050000 | errno.EPERM
    try:
        for name in ('socket', 'socketpair', 'connect', 'bind', 'listen', 'accept', 'accept4',
                     'sendto', 'sendmsg', 'sendmmsg', 'recvfrom', 'recvmsg', 'recvmmsg',
                     'clone', 'clone3', 'fork', 'vfork', 'execve', 'execveat',
                     'kill', 'tkill', 'tgkill', 'ptrace', 'process_vm_readv', 'process_vm_writev',
                     'pidfd_open', 'pidfd_getfd', 'pidfd_send_signal', 'mount', 'umount2',
                     'pivot_root', 'open_by_handle_at', 'unshare', 'setns', 'bpf', 'userfaultfd',
                     'io_uring_setup', 'io_uring_enter', 'io_uring_register'):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and lib.seccomp_rule_add(ctx, deny, number, 0):
                raise RuntimeError('seccomp rule failed: ' + name)
        if lib.seccomp_load(ctx):
            raise RuntimeError('seccomp_load failed')
    finally:
        lib.seccomp_release(ctx)


def denied(call):
    try:
        obj = call()
    except OSError:
        return True
    if isinstance(obj, int):
        os.close(obj)
    elif hasattr(obj, 'close'):
        obj.close()
    return False


def main():
    sys.stdin.isatty(); sys.stdout.isatty()
    filter_syscalls()
    private_path = sys.argv[1]
    probes = {
        'private_path_read_denied': denied(lambda: os.open(private_path, os.O_RDONLY)),
        'private_parent_traversal_denied': denied(lambda: os.open('/proc/1/root' + private_path, os.O_RDONLY)),
        'network_socket_denied': denied(socket.socket),
        'process_signal_denied': denied(lambda: os.kill(1, 0)),
        'guard_source_write_denied': denied(lambda: os.open('/bench/scripts/benchmark_v0_attribute_guard_v1.py', os.O_WRONLY)),
    }
    if not all(probes.values()):
        print(json.dumps({'ready': False, 'probes': probes}), flush=True)
        return
    sys.path.insert(0, '/bench/scripts')
    from benchmark_v0_attribute_guard_v1 import evaluate
    print(json.dumps({'ready': True, 'probes': probes, 'sandbox_pid': os.getpid()}), flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = evaluate(request)
            print(json.dumps({'result': result}, ensure_ascii=False, allow_nan=False), flush=True)
        except Exception as exc:
            print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}), flush=True)


if __name__ == '__main__':
    main()
