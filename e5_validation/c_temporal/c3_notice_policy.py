"""E5-C C3: conditional cache invalidation using native notices.

Conditional T0 upper bound:
A privileged collector supplies a complete, ordered, check-time-settled
stream of every bound-knob mutation since the protected snapshot.

This assumption is NOT proven by the notice list itself.
No Unity private truth, state_version, online LLM or cryptographic claim.
"""
from __future__ import annotations

from e4_validation.protocol import (
    canonical, critical_action, monitor,
)

ARMS = (
    "C3_1_invalidate_only",
    "C3_2_notify_then_fresh",
)


def _fallback(mode, reason):
    return {
        "final": (
            "DEFER" if mode == ARMS[0]
            else "PENDING_FRESH"
        ),
        "needs_query": mode == ARMS[1],
        "cache_valid": False,
        "reason": reason,
    }


def decide(
    cache, candidate, case, stream, *,
    mode,
    capture_verified,
    access_granted,
    continuous_from_capture,
    settled_through_check,
    exclusive_writer,
):
    """Decide from cached evidence and explicitly delivered notices.

    Coverage flags must be established externally by the privileged
    experimental collector. They are NOT self-attesting evidence.

    stream: list of {"seq": int, "receipt": native_receipt}.
    The trusted adapter assigns the sequence number.
    """
    if mode not in ARMS:
        raise ValueError("Unknown C3 arm")

    if (
        case.get("family") != "attribute"
        or candidate != critical_action(case)
    ):
        return {
            "final": "DEFER",
            "needs_query": False,
            "cache_valid": False,
            "reason": "OUT_OF_SCOPE",
        }

    if not (
        capture_verified
        and isinstance(cache, dict)
        and cache.get("source_id")
        == "X_protected_native_Pass"
    ):
        return _fallback(mode, "UNVERIFIED_CAPTURE")

    if not (
        access_granted
        and continuous_from_capture
        and settled_through_check
        and exclusive_writer
    ):
        return _fallback(mode, "UNPROVEN_COVERAGE")

    if not isinstance(stream, list):
        return _fallback(mode, "BAD_STREAM")

    invalidated = False

    for expected_seq, entry in enumerate(stream, start=1):
        if (
            not isinstance(entry, dict)
            or type(entry.get("seq")) is not int
            or entry["seq"] != expected_seq
        ):
            return _fallback(mode, "BAD_SEQUENCE")

        rec = entry.get("receipt")

        if (
            not isinstance(rec, dict)
            or not isinstance(rec.get("request"), dict)
        ):
            return _fallback(mode, "BAD_RECEIPT")

        req = rec["request"]
        kind = req.get("action")
        target = req.get("objectId")

        if (
            type(rec.get("success")) is not bool
            or rec.get("last_action") != kind
        ):
            return _fallback(mode, "AMBIGUOUS_RECEIPT")

        if kind in (
            "ToggleObjectOn",
            "ToggleObjectOff",
        ):
            if target != case["knob_id"]:
                continue

            if req.get("forceAction") is not False:
                return _fallback(mode, "UNEXPECTED_FORCE")

            if rec["success"]:
                # Any successful bound-knob mutation makes the
                # ORIGINAL snapshot invalid. Do not infer that
                # its old value has been restored.
                invalidated = True

        elif kind in (
            "Pass",
            "GetReachablePositions",
            "TeleportFull",
        ):
            # These do not mutate the bound knob in the
            # scoped C1/C3 experimental contract.
            continue

        else:
            # Never infer "no change" from an unclassified action.
            return _fallback(mode, "UNCLASSIFIED_ACTION")

    if invalidated:
        return _fallback(mode, "BOUND_STATE_CHANGED")

    verdict = monitor(
        canonical(cache), candidate, case
    )

    return {
        "final": verdict,
        "needs_query": False,
        "cache_valid": verdict != "DEFER",
        "reason": (
            "COMPLETE_NO_RELEVANT_CHANGE"
            if verdict != "DEFER"
            else "INCOMPLETE_POLICY_FACT"
        ),
    }


def finish_fresh(
    pending, fresh_state, query_receipt,
    candidate, case,
):
    """Finish an authorized fallback after the runner issues Pass."""
    if (
        pending.get("final") != "PENDING_FRESH"
        or not pending.get("needs_query")
    ):
        raise ValueError("No authorized pending query")

    rec = (
        query_receipt.get("receipt")
        if isinstance(query_receipt, dict)
        else None
    )

    if (
        not isinstance(rec, dict)
        or rec.get("success") is not True
        or rec.get("last_action") != "Pass"
        or not isinstance(rec.get("request"), dict)
        or rec["request"].get("action") != "Pass"
        or not isinstance(fresh_state, dict)
        or fresh_state.get("source_id")
        != "X_protected_native_Pass"
    ):
        return "DEFER"

    return monitor(
        canonical(fresh_state), candidate, case
    )
