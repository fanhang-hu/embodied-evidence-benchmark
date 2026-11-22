"""Replay frozen Heldout LLM plans through the existing T0 Unity runner.

No new LLM requests, plan repair, or replacement Monitor/Executor.
"""

import argparse
import collections
import hashlib
import json
import traceback
from pathlib import Path

from e4_validation import pairs
from e4_validation.llm_shadow import build_prompt, extract_json, sha
from e4_validation.simulator import ROOT, start_controller

FREEZE = ROOT / "results/E4/06_followup_20261022/heldout_inputs_01"
CASES = ROOT / "results/E4/06_followup_20261022/heldout_freeze_01/heldout_catalogue.jsonl"
LIVE = ROOT / "results/E4/07_heldout/heldout_llm_01"


def readlines(path):
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def hexdigest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight():
    manifest = json.loads((FREEZE / "manifest.json").read_text())
    requests_path = FREEZE / "requests.jsonl"

    assert hexdigest(requests_path) == manifest["artifact_sha256"][
        str(requests_path.relative_to(ROOT))
    ]

    jobs = readlines(requests_path)
    records = readlines(LIVE / "records.jsonl")
    catalogue = {
        c["case_id"]: c for c in readlines(CASES)
    }

    assert len(jobs) == len(records) == 32
    assert len(catalogue) == 8
    assert len({j["request_sha256"] for j in jobs}) == 22

    mapping = {
        (r["case_id"], r["safe_initial"], r["condition"]): r
        for r in records
    }
    assert len(mapping) == 32

    selected = []

    for job in jobs:
        key = (
            job["case_id"],
            job["safe_initial"],
            job["condition"]
        )

        record = mapping[key]
        case = catalogue[job["case_id"]]

        assert case["status"] == "VALID"
        assert job["family"] == case["family"]
        assert job["condition"] in ("clean", "shared")

        for k in (
            "request_sha256",
            "source_state_sha256",
            "private_truth_sha256",
        ):
            assert job[k] == record[k], (key, k)

        body = job["request_body"]
        assert sha(body) == job["request_sha256"]

        public = json.loads(
            (ROOT / job["source_input_path"]).read_text()
        )
        assert sha(public) == job["source_state_sha256"]

        private_path = (
            ROOT / job["source_input_path"]
        ).with_name("producer_clean_private_eval_only.json")

        assert sha(json.loads(private_path.read_text())) == \
            job["private_truth_sha256"]

        prompt = json.loads(
            body["messages"][1]["content"]
        )
        assert build_prompt(public, case) == prompt

        response_path = (
            LIVE / "responses" /
            (job["request_sha256"] + ".json")
        )
        response = json.loads(response_path.read_text())

        assert record["status"] == response["status"] == "OK"
        assert response["finish_reason"] == "stop"

        actions = record["actions"]
        assert extract_json(response["raw_response"]) == {
            "actions": actions
        }

        assert isinstance(actions, list)
        assert len(actions) <= 16

        assert all(
            type(a) is dict
            and set(a) == {"action", "objectId"}
            and a in prompt["allowed_actions"]
            for a in actions
        )

        selected.append((job, case, actions, prompt))

    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--case-id",
        help="Pilot only; omit for complete 32-job Heldout"
    )
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    full = preflight()

    trials = [
        x for x in full
        if not args.case_id or x[0]["case_id"] == args.case_id
    ]

    if not trials:
        parser.error("Unknown case ID")

    print(
        "PREFLIGHT PASS:",
        len(full), "frozen jobs;",
        len(trials), "selected",
        flush=True
    )

    if args.dry_run:
        return

    out = args.out.resolve()

    if out.exists() or not out.is_relative_to(ROOT):
        parser.error(
            "Output must be NEW and under ~/embodied"
        )

    out.mkdir(parents=True, exist_ok=False)

    pairs.write_json(
        out / "run_manifest.json",
        dict(
            protocol="frozen_T0_heldout_original_monitor_native_Unity",
            model_calls=0,
            selection=(
                "ALL_FROZEN"
                if args.case_id is None
                else "PILOT_ONLY"
            ),
            n=len(trials),
            total_frozen=len(full),
            inputs_sha256=hexdigest(FREEZE / "requests.jsonl"),
            llm_records_sha256=hexdigest(LIVE / "records.jsonl"),
            catalogue_sha256=hexdigest(CASES),
            code_sha256=hexdigest(Path(__file__)),
        )
    )

    controller = None
    rows = []

    try:
        controller = start_controller(trials[0][1]["scene"])

        for idx, (job, case, actions, prompt) in enumerate(trials):

            episode_dir = out / "episodes" / (
                "%02d_%s_%s_%s" % (
                    idx,
                    job["case_id"],
                    "safe" if job["safe_initial"] else "unsafe",
                    job["condition"]
                )
            )

            normalized = [
                dict(a, forceAction=False)
                for a in actions
            ]

            source = dict(
                request_sha256=job["request_sha256"],
                raw_plan_actions=actions,
                normalized_actions=normalized,
                public_prompt_sha256=job["prompt_sha256"],
            )

            previous_plan = pairs.plan

            def archived_plan(serialized_state, runtime_case):
                assert runtime_case["case_id"] == case["case_id"]

                live_state = json.loads(serialized_state)

                assert build_prompt(live_state, runtime_case) == prompt, \
                    "LIVE_PUBLIC_PROMPT_DIFFERS_FROM_FROZEN_PROMPT"

                return dict(
                    status="PLAN" if normalized else "ABSTAIN",
                    actions=normalized,
                    planner="archived_real_LLM",
                    request_sha256=job["request_sha256"]
                )

            try:
                # Replace only the deterministic planner output.
                # Existing Monitor and Executor remain unchanged.
                pairs.plan = archived_plan

                row = pairs.run_episode(
                    controller,
                    case,
                    job["safe_initial"],
                    job["condition"],
                    episode_dir,
                )

                row["status"] = "COMPLETED"
                row["archived_plan_source"] = source
                row["run_uses_archived_real_llm"] = True
                row["original_monitor_unchanged"] = True
                row["no_new_llm_calls"] = True

                pairs.write_json(
                    episode_dir / "llm_source.json",
                    source
                )
                pairs.write_json(
                    episode_dir / "episode.json",
                    row
                )

            except Exception as exc:
                row = dict(
                    case_id=job["case_id"],
                    family=job["family"],
                    safe_initial=job["safe_initial"],
                    condition=job["condition"],
                    status="FAILED_OR_INCOMPLETE",
                    error=repr(exc),
                    traceback=traceback.format_exc()
                )

                episode_dir.mkdir(
                    parents=True,
                    exist_ok=True
                )
                pairs.write_json(
                    episode_dir / "failure.json",
                    row
                )

            finally:
                pairs.plan = previous_plan

            rows.append(row)

            with (out / "records.jsonl").open("a") as f:
                f.write(
                    json.dumps(row, ensure_ascii=False) + "\n"
                )

            print(
                "%02d/%02d" % (idx + 1, len(trials)),
                job["case_id"],
                job["safe_initial"],
                job["condition"],
                row["status"],
                "UAR=", row.get("unsafe_authorized"),
                "ExecViolation=", row.get("violation_executed"),
                flush=True
            )

    finally:
        if controller is not None:
            controller.stop()

        summary = dict(
            total=len(rows),
            expected=len(trials),
            status_counts=dict(
                collections.Counter(
                    r["status"] for r in rows
                )
            ),
            full_heldout=args.case_id is None,
            unsafe_authorized=sum(
                bool(r.get("unsafe_authorized"))
                for r in rows
            ),
            execution_violations=sum(
                bool(r.get("violation_executed"))
                for r in rows
            ),
            defense="original_monitor",
            online_model_calls=0
        )

        pairs.write_json(
            out / "summary.json",
            summary
        )
        print("SUMMARY:", summary, flush=True)

    if (
        len(rows) != len(trials)
        or any(r["status"] != "COMPLETED" for r in rows)
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
