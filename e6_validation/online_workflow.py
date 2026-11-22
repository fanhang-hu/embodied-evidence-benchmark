"""Load bashrc configuration, run the frozen matrix, audit and report it."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import socket
import subprocess
import sys
from types import SimpleNamespace

from e5_validation.common import ROOT
from e6_validation.online_report import create_report
from e6_validation.online_runtime import check_protocol, run
from e6_validation.online_session import error_record, provider_config


DEFAULT_PROTOCOL = "results/E6/32_online_protocol/heldout_durable_20261025_01/protocol.json"
DEFAULT_RUN = "results/E6/33_online_native/heldout_durable_20261025_01"


def load_bashrc():
    names = ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "E4_LLM_BASE_URL", "E4_LLM_MODEL")
    marker = "__E6_PROVIDER_ENV__"
    code = "import os,json; print(" + repr(marker) + "+json.dumps({k:os.environ.get(k) for k in " + repr(names) + "}))"
    result = subprocess.run(["bash", "-ic", 'set +x; exec "$1" -c "$2"', "e6-provider", sys.executable, code],
                            capture_output=True, text=True, timeout=30)
    lines = [line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker)]
    if result.returncode or len(lines) != 1:
        raise RuntimeError("Bashrc configuration capture failed; shell output suppressed")
    config = json.loads(lines[0])
    for name in names:
        if config.get(name):
            os.environ[name] = config[name]
        else:
            os.environ.pop(name, None)


def preflight(protocol):
    load_bashrc()
    if provider_config() != protocol["provider_config"]:
        return dict(status="PROVIDER_CONFIG_DIFFERS_FROM_FROZEN_PROTOCOL", requests_made=0)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            pass
    except OSError as exc:
        return dict(status="LOCAL_SOCKET_UNAVAILABLE", error=error_record(exc), requests_made=0,
                    bashrc_loaded=True, provider_matches_frozen=True)
    return dict(status="LOCAL_PREFLIGHT_PASSED", requests_made=0, bashrc_loaded=True,
                provider_matches_frozen=True, API_connectivity_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default=DEFAULT_PROTOCOL)
    parser.add_argument("--run", default=DEFAULT_RUN)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="No API requests, Unity or output directory creation")
    mode.add_argument("--report-only", action="store_true", help="Audit/report existing results without API access")
    args = parser.parse_args()
    protocol = check_protocol(ROOT / args.protocol)
    if not args.report_only:
        result = preflight(protocol)
        print(json.dumps(result), flush=True)
        if result["status"] != "LOCAL_PREFLIGHT_PASSED":
            raise SystemExit(2)
        if args.check:
            return
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        run(SimpleNamespace(protocol=args.protocol, out=args.run, limit=protocol["expected"]))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    out, summary = create_report(ROOT / args.protocol, ROOT / args.run,
                                 "results/E6/36_online_report/online_" + stamp)
    print(summary["status"], out / "summary.json", flush=True)
    if not summary["native_online_matrix_verified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
