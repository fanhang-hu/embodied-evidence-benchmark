"""Conservative scene mention inventory; absence is never proof of novelty."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha

INDEX = ROOT / 'results/benchmark_v0/development_index_20261122_01/cases.jsonl'
MAX_BYTES = 16 * 1024 * 1024
PATTERN = re.compile(r'(?<![A-Za-z0-9_])FloorPlan([0-9]+)(?![A-Za-z0-9])|(?<=_)FloorPlan([0-9]+)(?![A-Za-z0-9])')


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', required=True)
    args = ap.parse_args(); out = checked_path(args.out)
    cases = [json.loads(line) for line in INDEX.read_text().splitlines() if line.strip()]
    if len(cases) != 12 or len({c['case_id'] for c in cases}) != 12: raise ValueError('Development index changed')
    for c in cases:
        if sha(ROOT / c['source_path']) != c['source_sha256']: raise ValueError('Historical source changed')
    paths = set((ROOT / 'share-pool').glob('*.md'))
    for stage in ('E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'benchmark_v0'):
        root = ROOT / 'results' / stage
        if root.is_dir():
            for glob in ('*protocol*.json', '*summary*.json', '*catalogue*.jsonl'):
                paths.update(root.rglob(glob))
    paths.add(INDEX)
    mentions, skipped = {}, []
    for path in sorted(paths):
        if not path.is_file(): continue
        rel = str(path.relative_to(ROOT))
        if path.stat().st_size > MAX_BYTES:
            skipped.append({'path': rel, 'reason': 'larger_than_16_mib'}); continue
        try: raw = path.read_bytes(); data = raw.decode('utf-8')
        except (UnicodeDecodeError, OSError):
            skipped.append({'path': rel, 'reason': 'unreadable_or_non_utf8'}); continue
        scenes = {'FloorPlan' + (a or b) for a, b in PATTERN.findall(data)}
        for scene in scenes:
            mentions.setdefault(scene, []).append({'path': rel, 'sha256': hashlib.sha256(raw).hexdigest()})
    by_scene = {}
    for c in cases: by_scene.setdefault(c['scene'], []).append({'case_id': c['case_id'], 'family': c['family'],
                                                               'source_path': c['source_path'], 'source_locator': c['source_locator'],
                                                               'source_sha256': c['source_sha256']})
    scenes = sorted(set(mentions) | set(by_scene), key=lambda x: int(x.removeprefix('FloorPlan')))
    records = [dict(scene=s, status='observed_development' if s in by_scene else 'mentioned_requires_review',
                    indexed_development_cases=by_scene.get(s, []), mention_sources=mentions.get(s, [])) for s in scenes]
    result = dict(schema='embodied.evidence_benchmark.scene_inventory.v1',
                  source_index_sha256=sha(INDEX), scanner_sha256=sha(Path(__file__).resolve()),
                  scanned_sources=len(paths)-len(skipped), skipped_sources=skipped,
                  matched_scenes=len(records), indexed_development_scenes=len(by_scene),
                  selection_scope=['share-pool root markdown', 'results/E1-E6 and results/benchmark_v0 recursively: filenames containing protocol or summary JSON, catalogue JSONL', 'development case index'],
                  interpretation='A mention is not proof of a run. Absence is not evidence a scene was never observed; other sources, private data and runs are not scanned.',
                  records=records)
    out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    path = out / 'inventory.json'; path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n'); os.chmod(path, 0o600)
    print('INVENTORY', len(records), 'SCENES', len(by_scene), 'INDEXED_DEVELOPMENT', 'SCANNED', result['scanned_sources'], 'SKIPPED', len(skipped))
    for row in records:
        print(row['scene'], row['status'], 'cases', len(row['indexed_development_cases']), 'sources', len(row['mention_sources']))

if __name__ == '__main__': main()
