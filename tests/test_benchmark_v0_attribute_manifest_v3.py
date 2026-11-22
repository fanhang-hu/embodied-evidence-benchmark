from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_attribute_native_v3 import build_protocol, checked_manifest, load_cases


class AttributeManifestTests(unittest.TestCase):
    def test_manifest_cases_produce_complete_matrix(self):
        path = checked_manifest('benchmark_v0/cases/attribute_relation_scenes_20261122.jsonl')
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        ids = [r['case_id'] for r in rows]
        protocol = build_protocol(ids, path)
        self.assertEqual(protocol['expected'], len(ids) * 12)
        self.assertEqual(len({(x['case_id'], x['condition'], x['arm']) for x in protocol['assignments']}), len(ids) * 12)
        self.assertIn(str(path.relative_to(ROOT)), protocol['source_sha256'])

    def test_duplicate_manifest_ids_and_wrong_family_rejected(self):
        case = dict(case_id='case_1', scene='FloorPlan1', family='relation', pan_id='p', burner_id='b', knob_id='k')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'cases.jsonl'
            path.write_text(json.dumps(case) + '\n')
            with self.assertRaises(ValueError):
                load_cases(['case_1'], path)
            case['family'] = 'attribute'
            path.write_text((json.dumps(case) + '\n') * 2)
            with self.assertRaises(ValueError):
                load_cases(['case_1'], path)

    def test_manifest_outside_allowed_roots_rejected(self):
        with tempfile.NamedTemporaryFile() as source:
            with self.assertRaises(ValueError):
                checked_manifest(source.name)


if __name__ == '__main__':
    unittest.main()
