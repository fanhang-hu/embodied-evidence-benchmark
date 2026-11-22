#!/usr/bin/env python3
"""Check the reorganization without running models, simulators, or old writers."""
import ast
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify():
    mapping = json.loads((ROOT / 'organization_audit/path_map.json').read_text())
    protected = json.loads((ROOT / 'organization_audit/protected_artifacts_sha256.json').read_text())
    errors = []
    parsed = 0
    for old, new in mapping.items():
        path = ROOT / new
        if not path.is_file():
            errors.append('Missing migrated source: ' + new)
            continue
        if (ROOT / old).is_file():
            errors.append('Duplicate historical entrypoint: ' + old)
        if path.suffix != '.py':
            continue
        try:
            tree = ast.parse(path.read_text(), filename=new)
            parsed += 1
        except SyntaxError as exc:
            errors.append(str(exc))
            continue
        if not (path.parent / '_bootstrap.py').is_file():
            errors.append('Missing bootstrap: ' + new)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if ('\n' not in value and value.endswith('.py') and
                    value.startswith(('scripts/', 'e1_validation/', 'e2_validation/', 'e3_baseline/')) and
                    not (ROOT / value).is_file()):
                    errors.append(f'{new}:{node.lineno}: unresolved script {value}')
    for relative, expected in protected.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append('Missing original artifact: ' + relative)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append('Original artifact changed: ' + relative)
    baselines = sorted((ROOT / 'e3_baseline').glob('b[1-9]_*'))
    if len(baselines) != 9:
        errors.append('Expected exactly nine baseline directories')
    csv_rows = list(csv.reader((ROOT / 'share-pool/baseline.csv').open(encoding='utf-8-sig')))
    original_names = {int(r[0][1:]):r[1] for r in csv_rows if r and r[0].startswith('#') and r[0][1:].isdigit()}
    for d in baselines:
        m = json.loads((d / 'manifest.json').read_text())
        if m['name'] != original_names.get(m['baseline_number']):
            errors.append('CSV numbering/name mismatch: ' + d.name)
        for name in ('README.md', 'run.sh', 'manifest.json'):
            if not (d / name).is_file():
                errors.append('Missing ' + str(d / name))
        for p in m['evidence']:
            if not (ROOT / p).is_file():
                errors.append('Missing baseline evidence: ' + p)
    return {'migrated_files':len(mapping),'python_files_parsed':parsed,
            'protected_artifacts_checked':len(protected),'baseline_directories':len(baselines),
            'errors':errors,'ok':not errors}


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['ok'] else 1)
