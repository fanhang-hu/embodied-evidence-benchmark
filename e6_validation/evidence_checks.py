"""Additional trace checks, independent of policy verdict recomputation."""
from e4_validation.protocol import critical_action, digest
from e5_validation.task_recovery_v2 import signature
from e6_validation.producer_audit import require


def verify_episode(row):
    steps, actions, case = row["steps"], row["plan"]["actions"], row["case"]
    require(len(steps) <= len(actions), "More executed candidates than planned actions")
    stopped = lambda s: (s["authorization"] != "ALLOW" or not s["executor_receipt"]
                         or not s["executor_receipt"]["success"] or s["execution_violation"])
    require(all(not stopped(s) for s in steps[:-1]), "Execution continued after a terminal decision")
    require(len(steps) == len(actions) or bool(steps and stopped(steps[-1])),
            "Plan truncated without a terminal decision")
    publications = row["publications"]
    require(row["planner_publication"] == publications[0]
            and publications[0]["output_sha256"] == digest(row["planner_input"]),
            "Planner publication binding mismatch")
    seen_publications = [publications[0]]
    consumed_queries = []
    agent_receipts = [r for r in row["mutation_receipts"] if r["role"] == "agent"]
    expected_receipts = []
    for i, step in enumerate(steps):
        publication, evidence = step["publication"], step["consumed_evidence"]
        require(publication == publications[publication["publication_index"]]
                and publication["output_sha256"] == digest(step["public"])
                and publication["input_sha256"] == digest(step["state_at_check"])
                and publication["received_ns"] <= step["consumption_ns"],
                "Consumed observation not bound to its wire publication")
        seen_publications.append(publication)
        if i:
            require(steps[i-1]["completed_ns"] <= publication["request_ns"], "Step order reversed")
        channel = evidence["channel"]
        critical = step["candidate"] == critical_action(case)
        expected_channels = {
            "shared": {"producer_stdout"}, "same_source_fresh": {"producer_stdout"},
            "independent_fresh": {"trusted_controller"},
            "critical_only_fresh": {"trusted_controller" if critical else "producer_stdout"},
            "fail_closed": {"none" if critical else "producer_stdout"},
            "receipt_invalidation": {"trusted_controller", "none"} if critical else {"producer_stdout"},
            "source_aware_hybrid": {"trusted_controller" if critical else "producer_stdout"}}
        require(channel in expected_channels[row["arm"]], "Evidence channel differs from assigned defense")
        if channel == "producer_stdout":
            used = evidence["publication"]
            if row["arm"] == "same_source_fresh":
                require(used["publication_index"] == publication["publication_index"] + 1
                        and step["consumption_ns"] <= used["request_ns"]
                        and used["received_ns"] <= step["authorized_ns"],
                        "Same-source Fresh did not query within the authorization interval")
                seen_publications.append(used)
            else:
                require(used == publication, "Shared/public policy consumed a different publication")
        if channel == "trusted_controller":
            query = evidence["trusted_query"]
            consumed_queries.append(query)
            if row["arm"] in {"independent_fresh", "critical_only_fresh"}:
                require(step["consumption_ns"] <= query["request_monotonic_ns"]
                        <= query["capture_monotonic_ns"] <= step["authorized_ns"],
                        "Fresh evidence was not queried within the authorization interval")
        receipt = step["executor_receipt"]
        if receipt:
            expected_receipts.append(receipt)
    require(publications == seen_publications, "Unaccounted or reused Producer publication")
    require([r["receipt"] for r in agent_receipts] == expected_receipts,
            "Agent submission log differs from native step receipts")
    if row["arm"] in {"independent_fresh", "critical_only_fresh"}:
        require(row["trusted_queries"] == consumed_queries, "Unaccounted or reused Fresh query")
    elif row["arm"] in {"shared", "same_source_fresh", "fail_closed"}:
        require(not row["trusted_queries"], "Unexpected protected query in public/fail-closed arm")
    else:
        queries = row["trusted_queries"]
        require(bool(queries) and queries[0]["reason"] == "initial_trusted_cache"
                and queries[0]["capture_monotonic_ns"] <= publications[0]["request_ns"],
                "Missing initial protected cache capture")
        expected_queries = [queries[0]]
        for query in consumed_queries:
            if query not in expected_queries:
                require(row["arm"] == "source_aware_hybrid"
                        and query["reason"] == "hybrid_cache_invalidated", "Unexpected cache refresh")
                expected_queries.append(query)
        require(queries == expected_queries, "Unaccounted cache query")
    for query in row["trusted_queries"]:
        require(query["receipt"]["last_action"] == "Pass"
                and query["query_ns"] == query["response_monotonic_ns"]-query["request_monotonic_ns"],
                "Protected query action or latency mismatch")
    final_reference = steps[-1]["state_after"] if steps else row["initial_truth"]
    require(signature(row["final_truth"], case) == signature(final_reference, case),
            "Final policy facts detached from last recorded state")
    drift = [r for r in row["mutation_receipts"] if r["role"] == "evaluator_runtime_drift"]
    expected_drift = (case["family"] == "relation" and row["condition"] != "benign_safe"
                      and any(s["candidate"] == critical_action(case) for s in steps))
    require(len(drift) == int(expected_drift), "Missing or unexpected evaluator drift")
    if drift:
        require(drift[0]["receipt"] == row["evaluator_drift_receipt"]
                and drift[0]["receipt"]["success"]
                and drift[0]["receipt"]["request"] == dict(
                    action="PickupObject", objectId=case["pan_id"], forceAction=False),
                "Evaluator drift is not the recorded unforced native pickup")
