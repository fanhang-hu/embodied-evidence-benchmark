"""Conditional-T0 experimental action proxy; not deployment authentication.

Records every Python controller.step call routed through this object
after a protected observation. Coverage assumes this is the sole writer.
Unobserved writers cannot be ruled out by the proxy itself.
"""
from __future__ import annotations

import copy
import time

from e4_validation.protocol import digest
from e4_validation.simulator import receipt


class NoticeProxy:
    def __init__(self, controller):
        self._controller = controller
        self._active = False
        self._sealed = False
        self._events = []
        self._capture_ns = None

    def __getattr__(self, name):
        return getattr(self._controller, name)

    def reset(self, *args, **kwargs):
        if self._active:
            raise RuntimeError(
                "Reset after capture violates continuity"
            )
        return self._controller.reset(*args, **kwargs)

    def step(self, **request):
        if self._sealed:
            raise RuntimeError(
                "Native action attempted after notification seal"
            )

        event = self._controller.step(**request)

        if self._active:
            self._events.append({
                "seq": len(self._events) + 1,
                "receipt": receipt(
                    event, copy.deepcopy(request)
                ),
                "observed_monotonic_ns":
                    time.perf_counter_ns(),
            })

        return event

    def start_after_capture(self, capture_query):
        if self._active:
            raise RuntimeError("Already capturing")

        rec = capture_query.get("receipt", {})

        if (
            rec.get("success") is not True
            or rec.get("last_action") != "Pass"
            or rec.get("request", {}).get("action")
            != "Pass"
        ):
            raise ValueError(
                "Capture must be successful native Pass"
            )

        self._capture_ns = (
            capture_query["capture_monotonic_ns"]
        )
        self._active = True

    def recorded(self):
        return copy.deepcopy(self._events)

    def seal(self, *, withheld_seq=None):
        if not self._active or self._sealed:
            raise RuntimeError(
                "Missing capture boundary or double seal"
            )

        self._sealed = True
        full = copy.deepcopy(self._events)

        if withheld_seq is not None:
            if not any(
                x["seq"] == withheld_seq for x in full
            ):
                raise ValueError(
                    "Withheld sequence absent"
                )

        delivered = [
            {
                "seq": entry["seq"],
                "receipt": entry["receipt"],
            }
            for entry in full
            if entry["seq"] != withheld_seq
        ]

        return {
            "capture_monotonic_ns": self._capture_ns,
            "seal_monotonic_ns": time.perf_counter_ns(),
            "full_history": full,
            "delivered_stream": delivered,
            "full_hash": digest(full),
            "delivered_hash": digest(delivered),
            "full_event_count": len(full),
            "delivered_event_count": len(delivered),
            "intentionally_withheld_seq": withheld_seq,
            "continuous_from_capture":
                withheld_seq is None,
            "access_granted": True,
            "settled_through_check": True,
            "exclusive_writer_assumed": True,
            "coverage_scope": (
                "Instrumented Python controller.step calls "
                "from capture to seal; no out-of-band writers "
                "assumed, not authenticated"
            ),
        }

    def begin_post_guard(self):
        """Allow an explicit fallback Pass or authorized action."""
        if not self._sealed:
            raise RuntimeError(
                "Unsealed notification stream"
            )

        self._sealed = False

        # Post-guard actions are outside the sealed interval.
        self._active = False
