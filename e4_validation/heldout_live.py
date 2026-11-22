"""E4 frozen Heldout LLM inference. No Unity or Monitor execution."""

import argparse
import collections
import hashlib
import json
import os
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

from e4_validation.llm_shadow import (
    sha, invoke, load_bashrc_provider, extract_json
)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_response(answer, body):
    if (
        answer.get("finish_reason") != "stop"
        or not isinstance(answer.get("raw_response"), str)
    ):
        return "INVALID_PROVIDER_OUTPUT", None

    try:
        obj = extract_json(answer["raw_response"])
        prompt = json.loads(body["messages"][1]["content"])
        allowed = prompt["allowed_actions"]

        if (
            not isinstance(obj, dict)
            or set(obj) != {"actions"}
            or not isinstance(obj["actions"], list)
        ):
            raise ValueError("Invalid actions structure")

        actions = obj["actions"]

        for action in actions:
            if (
                not isinstance(action, dict)
                or set(action) != {"action", "objectId"}
                or action not in allowed
            ):
                raise ValueError("Invalid action or target")

        return ("OK" if actions else "EMPTY_PLAN"), actions

    except (ValueError, KeyError, TypeError):
        return "INVALID_PLAN_FORMAT", None


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--root", type=Path,
        default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--inputs",
        default="results/E4/06_followup_20261022/heldout_inputs_01"
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--load-bashrc", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--max-calls", type=int, default=22)

    args = parser.parse_args()
    root = args.root.resolve()
    input_dir = (root / args.inputs).resolve()
    out = (root / args.out).resolve()

    if out.exists():
        parser.error(f"Output already exists: {out}")

    manifest_path = input_dir / "manifest.json"
    requests_path = input_dir / "requests.jsonl"

    manifest = json.loads(manifest_path.read_text())

    # Frozen data must remain unchanged.
    # Source-code drift is reported separately.
    for name, expected in manifest["artifact_sha256"].items():
        path = root / name

        if name.startswith("results/E4/"):
            if not path.is_file() or file_sha(path) != expected:
                raise SystemExit(
                    f"Frozen input changed or missing: {name}"
                )
        elif not path.is_file() or file_sha(path) != expected:
            print(f"WARNING: Source-code hash changed: {name}")

    jobs = [
        json.loads(line)
        for line in requests_path.read_text().splitlines()
        if line.strip()
    ]

    if len(jobs) != 32:
        raise SystemExit("Expected 32 frozen logical jobs")

    unique = {}

    for job in jobs:
        body = job["request_body"]
        key = job["request_sha256"]

        if sha(body) != key:
            raise SystemExit("Frozen request hash mismatch")

        prompt_text = body["messages"][1]["content"]

        if (
            hashlib.sha256(prompt_text.encode()).hexdigest()
            != job["prompt_sha256"]
        ):
            raise SystemExit("Frozen prompt hash mismatch")

        state_path = root / job["source_input_path"]

        if sha(json.loads(state_path.read_text())) != job["source_state_sha256"]:
            raise SystemExit("Frozen state hash mismatch")

        system_text = body["messages"][0]["content"]

        if (
            hashlib.sha256(system_text.encode()).hexdigest()
            != manifest["model"]["system_prompt_sha256"]
        ):
            raise SystemExit("Frozen system prompt mismatch")

        model = manifest["model"]

        if (
            body["model"] != model["requested_model"]
            or body["temperature"] != model["temperature"]
            or body["max_tokens"] != model["max_tokens"]
            or body.get("thinking") != {"type": "disabled"}
        ):
            raise SystemExit("Frozen model settings mismatch")

        if key in unique and unique[key] != body:
            raise SystemExit("Request hash collision/mismatch")

        unique[key] = body

    if (
        len(unique) != 22
        or len(unique) > args.max_calls
        or len({j["case_id"] for j in jobs}) != 8
        or {j["condition"] for j in jobs} != {"clean", "shared"}
    ):
        raise SystemExit("Unexpected Heldout configuration")

    print(
        f"PREFLIGHT PASS: {len(jobs)} logical jobs, "
        f"{len(unique)} unique requests",
        flush=True
    )

    if not args.live:
        print("DRY RUN: no API calls; no output files created")
        return

    if args.load_bashrc:
        load_bashrc_provider()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY unavailable")

    base = (
        args.base_url
        or os.environ.get("E4_LLM_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    )

    parsed = urllib.parse.urlsplit(base)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit("Invalid HTTPS API endpoint")

    provider = SimpleNamespace(
        base_url=base,
        api_key_env="DEEPSEEK_API_KEY",
        timeout=args.timeout
    )

    out.mkdir(parents=True, exist_ok=False)
    (out / "responses").mkdir()

    run_manifest = {
        "level": "T0_Heldout_LLM_only",
        "input_dir": str(input_dir.relative_to(root)),
        "requests_sha256": file_sha(requests_path),
        "freeze_manifest_sha256": file_sha(manifest_path),
        "script_sha256": file_sha(Path(__file__)),
        "model": manifest["model"],
        "logical_jobs": len(jobs),
        "unique_requests": len(unique),
        "monitor_tested": False,
        "unity_tested": False,
        "duplicates_not_independent": True
    }

    (out / "manifest.json").write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False)
    )

    answers = {}
    failed = False

    for index, (key, body) in enumerate(unique.items(), start=1):
        print(
            f"Request {index}/{len(unique)} "
            f"sha={key[:12]}",
            flush=True
        )

        try:
            answer = invoke(body, provider)

            status, actions = check_response(answer, body)

            answer["status"] = status
            answer["actions"] = actions

        except Exception as exc:
            secret = os.environ.get("DEEPSEEK_API_KEY", "")
            message = str(exc)

            if secret:
                message = message.replace(secret, "[REDACTED]")

            answer = {
                "status": "FAILED_PROVIDER_OR_NETWORK",
                "error": type(exc).__name__ + ": " + message[:300]
            }
            failed = True

        answers[key] = answer

        (out / "responses" / f"{key}.json").write_text(
            json.dumps(answer, ensure_ascii=False, indent=2)
        )

        print("  Status:", answer["status"], flush=True)

        if failed:
            print(
                "Provider failed: remaining requests not attempted.",
                flush=True
            )
            break

    records = []

    for job in jobs:
        key = job["request_sha256"]

        answer = answers.get(
            key,
            {"status": "NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE"}
        )

        record = {
            field: job[field]
            for field in (
                "case_id",
                "family",
                "scene",
                "safe_initial",
                "condition",
                "source_input_path",
                "source_state_sha256",
                "private_truth_sha256",
                "prompt_sha256",
                "request_sha256"
            )
        }

        record.update({
            "status": answer["status"],
            "actions": answer.get("actions"),
            "response_file": (
                f"responses/{key}.json"
                if key in answers else None
            )
        })

        records.append(record)

    with (out / "records.jsonl").open("w") as f:
        for record in records:
            f.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    reused = sum(
        sum(j["request_sha256"] == key for j in jobs) - 1
        for key in answers
    )

    summary = {
        "logical_jobs": len(jobs),
        "unique_requests": len(unique),
        "requests_attempted": len(answers),
        "responses_reused": reused,
        "status_counts": dict(
            collections.Counter(r["status"] for r in records)
        ),
        "provider_failure": failed,
        "monitor_tested": False,
        "unity_tested": False
    }

    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )

    print("RESULT:", out, flush=True)
    print("SUMMARY:", summary, flush=True)

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
