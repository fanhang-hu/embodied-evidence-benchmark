"""Read-only evidence extraction for the dated E1--E6 research report.

Writes new derived artifacts only. Does not import experiment code or start
Unity, models, generated guard code, or network requests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    output.relative_to(ROOT / 'results' / 'research_status')
    if output.exists():
        raise SystemExit('Output must be a new directory')
    sources = {}

    def read(path):
        data = (ROOT / path).read_bytes()
        sources[path] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    e4 = read('results/E4/08_summary/final_20261023/method_summary.json')
    e5 = read('results/E5/03_acceptance/acceptance_20261025_01/metrics.json')
    acceptance = read('results/E6/37_acceptance/scoped_20261025_01/acceptance.json')
    assert acceptance['scoped_E6_complete'] is True
    assert acceptance['total_main_track_episodes'] == 364
    assert not acceptance['required_work_remaining_within_scope']
    v3 = read('results/E6/26_runtime_report/e6_runtime_v3_20261025_02/summary.json')
    critical = read('results/E6/30_critical_fresh_report/comparison_20261025_01/summary.json')
    online = read('results/E6/33_online_native/heldout_durable_20261025_01/summary.json')
    online_review = read('results/E6/37_acceptance/scoped_20261025_01/online_review.json')
    assert online['completed'] == online['expected'] == 16
    assert sum(row['episodes'] for row in e4) == 96
    e6_rows = []
    for track in v3['tracks']:
        for group in track['groups']:
            e6_rows.append(dict(track=track['label'], source=track['source'], **group))
    for track in critical['tracks']:
        for group in track['groups']:
            if group['arm'] == 'critical_only_fresh':
                e6_rows.append(dict(track=track['label'] + '_critical_only',
                                    source=track['baseline_source']['run'], **group))
    for group in online['groups']:
        e6_rows.append(dict(track='heldout_online',
                            source='results/E6/33_online_native/heldout_durable_20261025_01',
                            **group))
    assert sum(row['completed_episodes'] for row in e6_rows) == 364

    baseline_rows = []
    for path in sorted((ROOT / 'e3_baseline').glob('b*/manifest.json')):
        relative = str(path.relative_to(ROOT))
        record = read(relative)
        baseline_rows.append(dict(number=record['baseline_number'], name=record['name'],
                                  implementation_level=record['implementation_level'],
                                  manifest=relative,
                                  readme=str(path.with_name('README.md').relative_to(ROOT))))
    assert [row['number'] for row in baseline_rows] == list(range(1, 10))
    baseline_evidence = [
        'results/E3/01_roboguard/e3_pair_consolidation.json',
        'results/E3/02_simple/e3a7_precommitted_map.json',
        'results/E3/04_contract/safegate/m5_paired_evaluation_v2.json',
        'results/E3/05_optional/robosafe/r6a_fusion_v1.json',
        'results/E3/05_optional/robosafe/r6b_dual_corruption_swap_v1.json',
        'results/E3/06_embguard/e3g_audit/e3g_audit_summary.json',
        'results/E3/07_percepttwin/e3g2_live_attack_fusion.json',
        'results/E3/07_percepttwin/e3g2_live_positive_fusion.json',
        'results/E3/05_hdguard/e5c_repeatability/e5c_summary.json',
        'results/E3/05_hdguard/e5d2_forced_slow_repeat/summary.json',
        'results/E3/05_hdguard/e5e_quality_gate/e5e_quality_gate_replay.json',
        'results/E3/selp/e3c_unsafe_authorization.json',
        'results/E3/selp/e4_constrained_decoding.json',
        'results/E3/07_percepttwin/p24b_native_plan.json',
        'results/E3/07_percepttwin/p25_feedback_replan.json',
        'results/E3/08_guardagent/e3j3_shared_pair.json',
        'results/E3/09_refinement_gap/r5l_final_summary.json',
    ]
    # Extract summaries only; do not copy model responses or prompts wholesale.
    evidence_keys = ('summary', 'metrics', 'confusion', 'status', 'implementation',
                     'physical_execution', 'actual_execution', 'completed_pairs',
                     'strict_pair_count', 'unity_task_success', 'model_calls')
    baseline_extracts = {}
    for path in baseline_evidence:
        record = read(path)
        baseline_extracts[path] = {key: record[key] for key in evidence_keys if key in record}

    manifests = [
        'results/E4/08_summary/final_20261023/source_artifacts_sha256.json',
        'results/E5/03_acceptance/acceptance_20261025_01/audited_input_sha256.json',
    ]
    for track in v3['tracks']:
        manifests.append(track['source'] + '/artifact_sha256.json')
    for track in critical['tracks']:
        manifests.append(track['baseline_source']['run'] + '/artifact_sha256.json')
    manifests.append('results/E6/33_online_native/heldout_durable_20261025_01/artifact_sha256.json')
    hash_results = []
    for manifest in manifests:
        expected = read(manifest)
        missing, mismatch = [], []
        for path, digest in expected.items():
            target = ROOT / path
            if not target.is_file():
                missing.append(path)
            elif hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                mismatch.append(path)
        hash_results.append(dict(manifest=manifest, entries=len(expected),
                                 missing=missing, mismatched=mismatch))
    for path, expected in acceptance['source_sha256'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path

    workbook = read('organization_audit/baseline_workbook_cells.json')
    appendix = [
        '# 九项 Baseline 历史实验明细附录', '',
        '来源：本地 baseline.xlsx 的既有单元格导出；本次逐行保留“实验明细”表内容。', '',
        '**这是历史流水，不是当前完成状态表。** 早期缺权重、待执行、旧下一步和后续成功记录',
        '可能同时存在；当前状态以主报告和各 baseline README 为准。行号为原工作表行号，',
        '一行不等于一个独立试验；不据此累计 UAR 或执行 ASR。', '',
        '[当前总报告](截至2026-10-26实验总报告-E1至E6与九项Baseline.md) · '
        '[原始工作簿](baseline.xlsx) · '
        '[单元格导出](../organization_audit/baseline_workbook_cells.json)', '',
        '| 原行 | Baseline | 阶段 | 实现／输入 | 检验问题 | 原记结果 | 限制／解释 | 原记证据路径 |',
        '|---:|---|---|---|---|---|---|---|',
    ]

    def escape(value):
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\r', '').replace('\n', '<br>')

    detail_rows = []
    for cells in workbook['实验明细']:
        row_number = int(''.join(c for c in next(iter(cells)) if c.isdigit()))
        if row_number == 4:
            continue
        values = [cells.get(f'{column}{row_number}', '') for column in 'ABCDEFG']
        detail_rows.append(dict(sheet_row=row_number, **dict(zip('ABCDEFG', values))))
        appendix.append('| ' + ' | '.join(map(escape, [row_number, *values])) + ' |')

    def flatten(record, prefix=''):
        result = {}
        for key, value in record.items():
            name = prefix + key
            if isinstance(value, dict):
                result.update(flatten(value, name + '_'))
            else:
                result[name] = value
        return result

    output.mkdir(parents=True)

    def write_json(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def write_csv(name, rows):
        rows = [flatten(row) for row in rows]
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (output / name).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write_csv('baseline_inventory.csv', baseline_rows)
    write_csv('baseline_historical_details.csv', detail_rows)
    write_csv('e4_method_metrics.csv', e4)
    write_csv('e5_group_metrics.csv', e5)
    write_csv('e6_group_metrics.csv', e6_rows)
    write_csv('e6_online_aggregate.csv', online_review['aggregates'])
    write_json('baseline_evidence_extracts.json', baseline_extracts)
    write_json('input_sha256.json', sources)
    write_json('historical_baseline_appendix.json', {'markdown': '\n'.join(appendix) + '\n'})
    differences = [(row['manifest'], path) for row in hash_results for path in row['mismatched']]
    # E4's broad historical inventory hashed the live root index too. That
    # index now explicitly records later E5/E6 completion; keep the difference
    # visible rather than editing the historical expected hash.
    index_drift_only = (all(not row['missing'] for row in hash_results)
                        and bool(differences)
                        and all(path == 'README.md' for _, path in differences))
    clean = all(not row['missing'] and not row['mismatched'] for row in hash_results)
    status = ('PASS_READ_ONLY_DOCUMENTATION_REVIEW' if clean else
              'PASS_EVIDENCE_HASHES_WITH_DOCUMENT_INDEX_DRIFT' if index_drift_only else
              'REVIEW_HASH_DIFFERENCES')
    audit = dict(status=status,
                 date='2026-10-26', new_Unity_runs=0, new_model_requests=0,
                 original_results_modified=False, baseline_count=9,
                 e4_formal_replay_episodes=96, e6_main_track_episodes=364,
                 e6_metric_rows=len(e6_rows), workbook_detail_rows_preserved=len(detail_rows),
                 hash_checks=hash_results,
                 document_drift_note=('E4 historical inventory differs only at the live root README.md, '
                                      'which now describes later E5/E6 results; historical hash unchanged'
                                      if index_drift_only else None),
                 acceptance_hashes_verified=len(acceptance['source_sha256']),
                 limitations=['This script extracts prior metrics; it does not rerun scientific audits or unit tests',
                              'Historical workbook statuses can be superseded',
                              'No pooled E1--E6 success rate or independent sample total'])
    write_json('audit.json', audit)
    write_json('generated_sha256.json', {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in sorted(output.iterdir()) if path.is_file()})
    print(json.dumps({key: audit[key] for key in ('status', 'baseline_count', 'e6_main_track_episodes',
                                               'e6_metric_rows', 'workbook_detail_rows_preserved')}, ensure_ascii=False))
    for row in hash_results:
        print(json.dumps({key: (len(value) if isinstance(value, list) else value)
                          for key, value in row.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
