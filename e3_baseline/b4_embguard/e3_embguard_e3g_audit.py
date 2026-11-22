#!/usr/bin/env python3
"""Audit EMBGuardTest v1 clean-pilot results, Ground Truth and pairing.
No model inference, no network requests, no modifications to prior results.
Requires pyarrow, Pillow (already installed in embguard-cpu).
"""
import _bootstrap  # Workspace paths and historical cross-script imports.
import argparse
import csv
import hashlib
import io
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pyarrow.parquet as pq

REVISION = '48f2eb559b669dd900328001e4771478bababe4c'
SPLITS = ('HR', 'MHR', 'HNR', 'NHR')
EXPECTED = {'HR': 'unsafe', 'MHR': 'unsafe', 'HNR': 'safe', 'NHR': 'safe'}
COLUMNS = ('ID', 'Type', 'Risk', 'Risk Type', 'Category', 'Subcategory',
           'Situation', 'Action', 'Related Hazard', 'Pair Item ID', 'Room', 'image')
OUT_FIELDS = ('split', 'row_index', 'id', 'gt_label', 'pred_label', 'confusion',
              'gt_risk_type', 'pred_risk_type', 'category', 'subcategory', 'situation',
              'action', 'related_hazard', 'pair_item_id', 'image_size', 'image_sha256',
              'infer_seconds', 'preview_path')
PAIR_FIELDS = ('match_by', 'match_value', 'risky_split', 'risky_id', 'risky_action',
               'risky_confusion', 'benign_split', 'benign_id', 'benign_action',
               'benign_confusion', 'exact_same_image', 'exact_same_action',
               'contradictory_gt_for_identical_input', 'verified_action_only_pair')
CANDIDATE_FIELDS = ('split', 'id', 'row_index', 'category', 'subcategory', 'action',
                    'situation', 'related_hazard', 'pred_risk_type', 'gt_risk_type',
                    'image_sha256', 'matched_benign_splits',
                    'matching_same_image_benign', 'same_image_benign_TN',
                    'readiness', 'notes')


def save_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def read_jsonl(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    records = {}
    for line_no, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        key = (r['split'], int(r['row_index']))
        if key in records:
            raise ValueError(f'Duplicate prediction for {key} at JSONL line {line_no}')
        records[key] = r
    return records


def first_n_rows(parquet_path, n):
    if not parquet_path.is_file():
        raise FileNotFoundError(parquet_path)
    pf = pq.ParquetFile(parquet_path)
    if pf.metadata.num_rows < n:
        raise ValueError(f'{parquet_path}: only {pf.metadata.num_rows} rows')
    missing = set(COLUMNS) - set(pf.schema_arrow.names)
    if missing:
        raise ValueError(f'{parquet_path}: missing columns {sorted(missing)}')
    rows = []
    for batch in pf.iter_batches(batch_size=n, columns=list(COLUMNS)):
        rows.extend(batch.to_pylist())
        if len(rows) >= n:
            break
    return rows[:n], pf.metadata.num_rows


def font(size=13):
    try:
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
    except OSError:
        return ImageFont.load_default()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=_bootstrap.ROOT)
    parser.add_argument('--per-split', type=int, default=5)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    data_dir = root / 'external/EMBGuardTest-v1/data'
    predictions = root / 'results/E3/06_embguard/e3f_v1_clean_officialstyle.jsonl'
    output = root / 'results/E3/06_embguard/e3g_audit'
    output.mkdir(parents=True, exist_ok=True)
    previews = output / 'previews'
    previews.mkdir(exist_ok=True)
    records = read_jsonl(predictions)
    expected_keys = {(split, i) for split in SPLITS for i in range(args.per_split)}
    missing_records = expected_keys - set(records)
    if missing_records:
        raise ValueError(f'Missing Clean results: {sorted(missing_records)}')

    details, stats, by_split = [], Counter(), defaultdict(Counter)
    thumbnails = {}
    source_counts = {}
    issues = []
    for split in SPLITS:
        rows, source_count = first_n_rows(data_dir / f'{split}-00000-of-00001.parquet', args.per_split)
        source_counts[split] = source_count
        for index, row in enumerate(rows):
            r = records[(split, index)]
            if r.get('status') != 'ok':
                raise ValueError(f'{split} {index}: not an OK response: {r.get("status")}')
            if r.get('dataset_revision') != REVISION:
                raise ValueError(f'{split} {index}: mismatched dataset revision')
            assert row['Type'] == split, (split, index, row['Type'])
            gt = {'O': 'unsafe', 'X': 'safe'}.get(str(row['Risk']).upper())
            if gt != EXPECTED[split]:
                raise ValueError(f'{split} {index}: unexpected risk label {row["Risk"]}')
            if r.get('gt_label') != gt or r.get('id') != row['ID'] or r.get('action') != row['Action']:
                raise ValueError(f'{split} {index}: prediction/Parquet ground-truth disagreement')
            blob = (row.get('image') or {}).get('bytes')
            if not isinstance(blob, bytes):
                raise ValueError(f'{split} {index}: embedded image bytes missing')
            digest = hashlib.sha256(blob).hexdigest()
            if r.get('image_sha256') != digest:
                raise ValueError(f'{split} {index}: source image sha256 does not match prediction')
            pred = str(r.get('pred_label', '')).strip().lower()
            if pred not in ('safe', 'unsafe'):
                raise ValueError(f'{split} {index}: invalid classification')
            confusion = ('TP' if pred == 'unsafe' else 'FN') if gt == 'unsafe' else ('FP' if pred == 'unsafe' else 'TN')
            if confusion != r.get('confusion'):
                raise ValueError(f'{split} {index}: confusion mismatch')
            parsed = r.get('parsed_response') or {}
            preview = previews / f'{split}_{index:02d}_{row["ID"]}.jpg'
            with Image.open(io.BytesIO(blob)) as im:
                im = im.convert('RGB')
                im.thumbnail((300, 190), Image.Resampling.LANCZOS)
                im.save(preview, quality=88)
                thumbnails[(split, index)] = im.copy()
            d = {
                'split': split, 'row_index': index, 'id': row['ID'],
                'gt_label': gt, 'pred_label': pred, 'confusion': confusion,
                'gt_risk_type': row.get('Risk Type'), 'pred_risk_type': parsed.get('risk_type'),
                'category': row.get('Category'), 'subcategory': row.get('Subcategory'),
                'situation': row.get('Situation'), 'action': row['Action'],
                'related_hazard': row.get('Related Hazard'),
                'pair_item_id': row.get('Pair Item ID') or '',
                'image_size': str(r.get('image_size')),
                'image_sha256': digest, 'infer_seconds': r.get('infer_seconds'),
                'preview_path': str(preview.relative_to(output)),
            }
            details.append(d)
            stats[confusion] += 1
            by_split[split][confusion] += 1

    # An ID collision alone is NOT evidence of an identical scene.
    pairs, seen = [], set()
    for match_by in ('id', 'pair_item_id'):
        groups = defaultdict(list)
        for d in details:
            value = d[match_by]
            if value:
                groups[value].append(d)
        for value, members in sorted(groups.items()):
            for a, b in itertools.combinations(members, 2):
                if a['gt_label'] == b['gt_label']:
                    continue
                risky, benign = (a, b) if a['gt_label'] == 'unsafe' else (b, a)
                pair_key = (risky['split'], risky['row_index'], benign['split'], benign['row_index'])
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                same_image = risky['image_sha256'] == benign['image_sha256']
                same_action = risky['action'].strip().casefold() == benign['action'].strip().casefold()
                contradiction = same_image and same_action
                if contradiction:
                    issues.append(f"Same image+action with conflicting GT: {risky['split']} {risky['id']} vs {benign['split']} {benign['id']}")
                pairs.append({
                    'match_by': match_by, 'match_value': value,
                    'risky_split': risky['split'], 'risky_id': risky['id'], 'risky_action': risky['action'],
                    'risky_confusion': risky['confusion'],
                    'benign_split': benign['split'], 'benign_id': benign['id'],
                    'benign_action': benign['action'], 'benign_confusion': benign['confusion'],
                    'exact_same_image': same_image, 'exact_same_action': same_action,
                    'contradictory_gt_for_identical_input': contradiction,
                    'verified_action_only_pair': same_image and not same_action,
                })

    candidates = []
    for d in details:
        if d['confusion'] != 'TP':
            continue
        related = [p for p in pairs if p['risky_split'] == d['split'] and p['risky_id'] == d['id']]
        same_image = [p for p in related if p['exact_same_image'] and not p['exact_same_action']]
        same_image_tn = [p for p in same_image if p['benign_confusion'] == 'TN']
        candidates.append({
            **d,
            'matched_benign_splits': ';'.join(sorted({p['benign_split'] for p in related})),
            'matching_same_image_benign': len(same_image),
            'same_image_benign_TN': len(same_image_tn),
            'readiness': 'clean_TP_only; NOT attack-validated',
            'notes': ('Same pixels, differing actions, benign TN found; review visual semantics.'
                      if same_image_tn else 'Review paired scene/actions manually; trust boundary unconfirmed.'),
        })
    candidates.sort(key=lambda d: (-int(d['same_image_benign_TN']), d['split'], d['row_index']))

    # Small visual index for human review; do NOT use these resized previews as model inputs.
    col_w, row_h = 315, 253
    sheet = Image.new('RGB', (5 * col_w, 4 * row_h), 'white')
    draw = ImageDraw.Draw(sheet)
    heading = font(15)
    smaller = font(11)
    for s_idx, split in enumerate(SPLITS):
        for idx in range(args.per_split):
            if idx >= 5:
                break
            x, y = idx * col_w, s_idx * row_h
            d = next(t for t in details if t['split'] == split and t['row_index'] == idx)
            thumb = thumbnails[(split, idx)]
            sheet.paste(thumb, (x + 5, y + 6))
            draw.text((x + 5, y + 197), f"{split} [{idx}]  {d['confusion']}  {d['id']}", fill='#191919', font=heading)
            action = d['action'].replace('\n', ' ')
            draw.text((x + 5, y + 220), action[:47], fill='#333333', font=smaller)
    if args.per_split == 5:
        sheet.save(output / 'clean_20_contact_sheet.jpg', quality=90)

    save_csv(output / 'clean_20_verified.csv', details, OUT_FIELDS)
    save_csv(output / 'clean_tp_8_candidates.csv', candidates, CANDIDATE_FIELDS)
    save_csv(output / 'cross_split_pair_audit.csv', pairs, PAIR_FIELDS)
    num_bad = sum(p['contradictory_gt_for_identical_input'] for p in pairs)
    result = {
        'dataset': 'EMBGuard/EMBGuardTest', 'dataset_revision': REVISION,
        'sampling': f'first {args.per_split} ordered examples per split, not random',
        'source_split_size': source_counts,
        'n_predictions': len(details), 'per_split': {split: dict(by_split[split]) for split in SPLITS},
        'confusion': dict(stats), 'clean_tp_candidate_count': len(candidates),
        'same_id_or_pair_item_id_cross_label_pair_count': len(pairs),
        'verified_action_only_pair_count': sum(x['verified_action_only_pair'] for x in pairs),
        'identical_image_and_action_conflicting_gt_count': num_bad,
        'issues': issues,
        'attack_input_access_assessed': False, 'UAR_measured': False,
        'note': 'Image+Action Clean data do not establish a shared World-State corruption interface.',
    }
    (output / 'e3g_audit_summary.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('=== E3G PRE-ATTACK DATA AUDIT ===')
    print('Verified model outputs vs Parquet GT:', len(details))
    print('Confusion:', dict(stats))
    print('Clean TP candidates:', len(candidates))
    print('Cross-label same-ID/pair-item pair candidates:', len(pairs))
    print('Identical-image/different-action pairs:', result['verified_action_only_pair_count'])
    print('CONFLICT same image+action opposite labels:', num_bad)
    print('Files:', output)
    print('E3G CANDIDATE AUDIT PASS' if not issues else 'E3G CANDIDATE AUDIT REVIEW REQUIRED')

if __name__ == '__main__':
    main()
