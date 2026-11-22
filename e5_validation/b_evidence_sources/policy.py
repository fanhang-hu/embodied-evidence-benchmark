"""E5-B authorization policy; no Unity or private evaluator truth.

Receipt availability and single-writer continuity are explicit
T0 experiment assumptions, not automatically proven by a receipt list.
"""

from e4_validation.protocol import canonical, critical_action, monitor
from e5_validation.receipt import receipt_guard

ARMS = ("B2_receipt_only", "B3_receipt_then_fresh")


def decide(
    public, candidate, case, receipts, *,
    arm, setup_log_granted, trace_continuous
):
    if arm not in ARMS:
        raise ValueError(f"Unknown E5-B arm: {arm}")

    if candidate.get("forceAction") is not False:
        return dict(
            raw="DEFER",
            receipt_decision="DEFER",
            sufficient=False,
            final="DEFER",
            needs_query=False,
            reason="force_action_not_allowed",
        )

    raw = monitor(canonical(public), candidate, case)

    # Preserve original policy for noncritical corrective actions.
    if candidate != critical_action(case):
        return dict(
            raw=raw,
            receipt_decision="NOT_APPLICABLE",
            sufficient=False,
            final=raw,
            needs_query=False,
            reason="noncritical_original_policy",
        )

    # Both conditions must be explicitly granted by the experiment.
    # A list of receipts cannot certify its own completeness.
    admissible = bool(setup_log_granted and trace_continuous)

    evidence = receipt_guard(
        receipts if admissible else [],
        case,
        complete_single_writer_trace=admissible,
    )

    if evidence["sufficient"]:
        return dict(
            raw=raw,
            receipt_decision=evidence["decision"],
            sufficient=True,
            final=evidence["decision"],
            needs_query=False,
            reason="bound_successful_receipt",
            supporting_receipt_indices=evidence.get(
                "supporting_receipt_indices", []
            ),
        )

    if arm == ARMS[0]:
        return dict(
            raw=raw,
            receipt_decision="DEFER",
            sufficient=False,
            final="DEFER",
            needs_query=False,
            reason=evidence["reason"],
        )

    # B3 may request one additional protected observation.
    # This is NOT an authorization yet.
    return dict(
        raw=raw,
        receipt_decision="DEFER",
        sufficient=False,
        final="PENDING_FRESH",
        needs_query=True,
        reason=evidence["reason"],
    )


def finish_query(pending, protected, candidate, case):
    """Finalize using the actual protected query, never private truth."""
    if (
        not pending["needs_query"]
        or pending["final"] != "PENDING_FRESH"
    ):
        raise ValueError("Fresh query not requested by policy")

    return monitor(canonical(protected), candidate, case)
