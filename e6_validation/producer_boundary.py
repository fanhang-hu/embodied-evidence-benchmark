"""Trusted receiver for the confined Producer's real JSON pipe transport."""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

from e4_validation.protocol import digest, field_diff


class Producer:
    def __init__(self, case, *, mode="pair", persistence="persistent", timeout=10):
        if mode not in {"clean", "single", "pair"}:
            raise ValueError("Unknown pollution mode")
        if persistence not in {"once", "persistent"}:
            raise ValueError("Unknown persistence")
        self.case = {k: case[k] for k in ("family", "pan_id", "burner_id", "knob_id")}
        self.mode, self.persistence, self.timeout = mode, persistence, timeout
        self.publications = []
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).with_name("producer_worker.py"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, close_fds=True, env={},
        )
        self._buffer = b""
        try:
            self.boundary = self._receive()
            if (self.boundary.get("ready") is not True or
                    self.boundary.get("producer_pid") != self.process.pid or
                    self.process.pid == os.getpid()):
                raise RuntimeError("Producer confinement unavailable: " + str(self.boundary))
            self.boundary["receiver_pid"] = os.getpid()
        except BaseException:
            self.close()
            raise

    def _receive(self):
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError("Producer response timed out")
            chunk = self.process.stdout.read(65536)
            if not chunk:
                raise RuntimeError("Producer exited before publishing evidence")
            self._buffer += chunk
            if len(self._buffer) > 16 * 1024 * 1024:
                raise ValueError("Producer message exceeds limit")
        line, self._buffer = self._buffer.split(b"\n", 1)
        return json.loads(line)

    def publish(self, observation):
        started = time.perf_counter_ns()
        message = dict(observation=observation, case=self.case, mode=self.mode,
                       persistence=self.persistence)
        self.process.stdin.write((json.dumps(message, allow_nan=False) + "\n").encode())
        answer = self._receive()
        received = time.perf_counter_ns()
        if "error" in answer:
            raise ValueError(answer["error"])
        view = answer["observation"]
        if (set(view) != set(observation) or
                any(view[k] != v for k, v in observation.items() if k != "objects") or
                len(view["objects"]) != len(observation["objects"]) or
                any(set(a) != set(b) or a["objectId"] != b["objectId"]
                    for a, b in zip(observation["objects"], view["objects"])) or
                answer["publication_index"] != len(self.publications)):
            raise ValueError("Producer exceeded the registered output schema")
        changes = field_diff(observation, view)
        c = self.case
        allowed = {(c["knob_id"], "isToggled")} if c["family"] == "attribute" else {
            (c["pan_id"], "parentReceptacles")}
        if self.mode == "pair":
            allowed.add((c["burner_id"], "isToggled") if c["family"] == "attribute"
                        else (c["pan_id"], "position"))
        if any((d["object_id"], d["field"]) not in allowed for d in changes):
            raise ValueError("Producer exceeded registered field permissions")
        record = dict(publication_index=answer["publication_index"],
                      channel="producer_stdout", trust="low_trust",
                      input_sha256=digest(observation), output_sha256=digest(view),
                      changes=changes, request_ns=started, received_ns=received,
                      roundtrip_ns=received-started)
        self.publications.append(record)
        # Provenance is attached by the receiver; the payload's source_id grants nothing.
        return view, record

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if self.process.stdout:
            self.process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
