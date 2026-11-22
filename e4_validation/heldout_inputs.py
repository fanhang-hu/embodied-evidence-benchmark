"""Freeze exact heldout observations/requests without API, policy or execution calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from e4_validation.llm_shadow import SYSTEM, build_prompt, make_request, sha
from e4_validation.pairs import write_json
from e4_validation.plan_replay import file_hash
from e4_validation.protocol import poison
from e4_validation.simulator import ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    freeze=args.freeze.resolve();out=args.out.resolve()
    if out.exists():raise SystemExit("Output already exists")
    manifest=json.loads((freeze/"heldout_manifest.json").read_text())
    assert manifest["status"]=="FROZEN_NATIVE_VALIDATED"
    for path,expected in manifest["artifact_sha256"].items():assert file_hash(ROOT/path)==expected
    cases=[json.loads(l) for l in (ROOT/manifest["catalogue"]).read_text().splitlines()]
    args_model=SimpleNamespace(model=manifest["model"]["requested_model"],max_tokens=manifest["model"]["max_tokens"])
    out.mkdir(parents=True,exist_ok=False)
    jobs=[]
    for case in cases:
        for trial in case["trials"]:
            safe=trial["expected_safe"]
            truth=dict(schema="e4.observation.v1",source_id="frozen_native_heldout_feasibility",state_version=0,objects=trial["S_true"])
            for condition in ("clean","shared"):
                public=truth if condition=="clean" else poison(truth,case)
                prompt=build_prompt(public,case)
                body=make_request(prompt,args_model)
                directory=out/"inputs"/case["case_id"]/("safe" if safe else "unsafe")/condition
                write_json(directory/"planner_input.json",public)
                write_json(directory/"producer_clean_private_eval_only.json",truth)
                write_json(directory/"prompt.json",prompt)
                jobs.append(dict(case_id=case["case_id"],family=case["family"],scene=case["scene"],safe_initial=safe,
                                 condition=condition,source_input_path=str((directory/"planner_input.json").relative_to(ROOT)),
                                 source_state_sha256=sha(public),private_truth_sha256=sha(truth),prompt_sha256=sha(prompt),
                                 request_sha256=sha(body),request_body=body))
    (out/"requests.jsonl").write_text("".join(json.dumps(j)+"\n" for j in jobs))
    files=[p for p in out.rglob('*') if p.is_file()]
    files += [freeze/"heldout_manifest.json",Path(__file__),ROOT/"e4_validation/llm_shadow.py",ROOT/"e4_validation/protocol.py"]
    write_json(out/"manifest.json",dict(status="FROZEN_INPUTS_NO_OUTCOMES",online_model_calls=0,Unity_calls=0,
               state_preparation_only=True,poisoning_scope="Offline deterministic T0 copies only; no heldout attack trial executed",
               task_configurations=len(cases),physical_object_target_configurations=len({(c['scene'],c['pan_id'],c['burner_id'],c['knob_id']) for c in cases}),
               logical_jobs=len(jobs),unique_public_requests=len({j["request_sha256"] for j in jobs}),
               source_freeze=str(freeze.relative_to(ROOT)),case_ids=[c['case_id'] for c in cases],
               policy=manifest["policy"],model=manifest["model"],system_prompt=SYSTEM,
               selection="All frozen cases retained regardless of future model response; no dangerous-plan screening on heldout",
               statistics_source="results/E4/06_followup_20261022/preregistration.json:Heldout.statistics",
               artifact_sha256={str(p.relative_to(ROOT)):file_hash(p) for p in files}))
    print("Frozen heldout requests:",len(jobs),"unique:",len({j["request_sha256"] for j in jobs}),"no API/Unity calls")


if __name__=="__main__":main()
