#!/usr/bin/env python3
"""E4 attribute pilot: same-input Knob/Burner consistency, FP3/FP4.

Reuses e4_validation.consistency_replay.run_filtered without modifying its
filter, the original policy, archived LLM plans, or the Unity executor.
Only the scenario/baseline selection is generalized from the FP2 pilot.
This is a T0 researcher-adapted experiment, not an official-system exploit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from pathlib import Path

from e4_validation import plan_replay as replay
from e4_validation.consistency_replay import run_filtered
from e4_validation.pairs import write_json
from e4_validation.simulator import ROOT, start_controller


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        '--case-id',
        required=True,
        choices=[
            'attribute_FloorPlan3_03',
            'attribute_FloorPlan4_13',
        ],
    )
    p.add_argument('--records', type=Path, required=True)
    p.add_argument(
        '--baseline-stage1',
        type=Path,
        required=True,
        help='Previously accepted C0/C2 replay directory',
    )
    p.add_argument(
        '--baseline-stage2',
        type=Path,
        required=True,
        help='Previously accepted C1/C3/C4 replay directory',
    )
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()

    out = args.out.resolve()

    if out.exists():
        p.error(f'Output already exists: {out}')

    try:
        out.relative_to(ROOT)
    except ValueError:
        p.error(f'--out must be inside project root: {ROOT}')

    cases_path = ROOT / 'configs/exp5/scenario_pilot.jsonl'

    cases = [
        json.loads(line)
        for line in cases_path.read_text().splitlines()
        if line.strip()
    ]

    candidates = [
        c for c in cases
        if c['case_id'] == args.case_id
        and c.get('status') == 'VALID'
        and c.get('family') == 'attribute'
    ]

    if len(candidates) != 1:
        p.error('Expected one valid frozen attribute pilot case')

    case = candidates[0]
    records_path = args.records.resolve()
    sources = replay.load_sources(records_path, case)

    mapping_path = (
        ROOT / 'results/E4/01_feasibility/'
        'run_20261022_headless_v3'
        / f'{case["scene"]}_mapping.json'
    )

    mapping = read_json(mapping_path)

    if (
        mapping['burner_to_knob'][case['burner_id']]
        != case['knob_id']
    ):
        raise RuntimeError(
            'Empirical burner/knob identity does not match frozen case'
        )

    prior = {}

    stage_paths = [
        args.baseline_stage1.resolve(),
        args.baseline_stage2.resolve(),
    ]

    required_sets = [
        {'C0', 'C2'},
        {'C1', 'C3', 'C4'},
    ]

    for stage, required_groups in zip(stage_paths, required_sets):
        summ = read_json(stage / 'summary.json')
        manifest = read_json(stage / 'frozen_manifest.json')

        if (
            not summ['all_expectations_passed']
            or set(summ['groups']) != required_groups
        ):
            raise RuntimeError(
                f'Baseline stage incomplete or mismatched: {stage}'
            )

        if manifest['sources'] != sources or manifest['case'] != case:
            raise RuntimeError(
                f'Baseline sources/case do not match frozen LLM records: {stage}'
            )

        for entry in summ['episodes']:
            if (
                entry['group'] in prior
                or not replay.expectation_passed(entry)
            ):
                raise RuntimeError(
                    'Duplicate or invalid prior baseline episode'
                )

            prior[entry['group']] = entry

    if set(prior) != {'C0', 'C1', 'C2', 'C3', 'C4'}:
        raise RuntimeError(
            'Five paired baselines not available'
        )

    frozen_files = [
        ROOT / 'scripts/e4_consistency_multiscene.py',
        ROOT / 'e4_validation/consistency.py',
        ROOT / 'e4_validation/consistency_replay.py',
        ROOT / 'e4_validation/plan_replay.py',
        ROOT / 'e4_validation/protocol.py',
        ROOT / 'e4_validation/pairs.py',
        ROOT / 'e4_validation/simulator.py',
        ROOT / 'e4_validation/llm_shadow.py',
        cases_path,
        ROOT / 'configs/exp5/security_policies.yaml',
        mapping_path,
        records_path,
        *(
            stage / filename
            for stage in stage_paths
            for filename in (
                'summary.json',
                'frozen_manifest.json',
            )
        ),
    ]

    hashes = {
        str(path.relative_to(ROOT)): file_hash(path)
        for path in frozen_files
    }

    out.mkdir(parents=True, exist_ok=False)

    for path in frozen_files:
        dest = out / 'frozen_sources' / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())

    write_json(
        out / 'frozen_manifest.json',
        dict(
            case=case,
            sources=sources,
            selected_groups=['C0', 'C2', 'C4'],
            baseline_stage1=str(stage_paths[0].relative_to(ROOT)),
            baseline_stage2=str(stage_paths[1].relative_to(ROOT)),
            source_file_sha256=hashes,
            online_model_calls=0,
            oracle_query_used=False,
            implementation=(
                'T0 researcher-adapted same-state consistency filter'
            ),
            executor='unchanged e4_validation.plan_replay.run_group',
        ),
    )

    results = []
    controller = None

    try:
        controller = start_controller(case['scene'])

        for group in ('C0', 'C2', 'C4'):
            folder = out / 'episodes' / group

            try:
                result = run_filtered(
                    controller,
                    case,
                    group,
                    sources[group],
                    folder,
                )

                old = prior[group]

                if (
                    result['initial_signature']
                    != old['initial_signature']
                    or result['normalized_plan_sha256']
                    != old['normalized_plan_sha256']
                ):
                    raise RuntimeError(
                        'Source plan/physical initial state '
                        'differs from original baseline'
                    )

                result['paired_baseline_matched'] = True

                if group in ('C0', 'C4'):
                    assert (
                        old['task_success']
                        and not old['violation_executed']
                    )

                if group == 'C2':
                    assert old['violation_executed']

            except Exception as exc:
                result = dict(
                    group=group,
                    status='FAILED_OR_INCOMPLETE',
                    defense_expectation_passed=False,
                    error=repr(exc),
                    traceback=traceback.format_exc(),
                )

                folder.mkdir(parents=True, exist_ok=True)

                write_json(
                    folder / 'failure.json',
                    result,
                )

            results.append(result)

            with (out / 'episodes.jsonl').open('a') as stream:
                stream.write(
                    json.dumps(result, ensure_ascii=False) + '\n'
                )

            print(
                group,
                result['status'],
                'defense_passed=',
                result['defense_expectation_passed'],
                'violation=',
                result.get('violation_executed'),
                result.get('error', ''),
                flush=True,
            )

            if not result['defense_expectation_passed']:
                break

    finally:
        if controller is not None:
            controller.stop()

        unchanged = all(
            file_hash(ROOT / key) == val
            for key, val in hashes.items()
        )

        passed = (
            len(results) == 3
            and all(
                r['defense_expectation_passed']
                and r.get('paired_baseline_matched')
                for r in results
            )
            and unchanged
        )

        write_json(
            out / 'summary.json',
            dict(
                case_id=case['case_id'],
                scene=case['scene'],
                passed=passed,
                episodes=results,
                original_sources_unchanged=unchanged,
                online_model_calls=0,
                oracle_query_used=False,
            ),
        )

    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
