"""Regression checks for path relocation and isolated experiment workspaces."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('experiment_launcher', ROOT / 'scripts/run_experiment.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class OrganizationTests(unittest.TestCase):
    def test_workspace_writes_do_not_change_archived_results(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            source.mkdir()
            for name in ('results', 'e1_validation', 'e2_validation', 'e3_baseline',
                         'experiment_tools', 'scripts', 'configs', 'external', 'share-pool'):
                (source / name).mkdir()
            original = source / 'results/evidence.json'
            original.write_text('{"original":true}')
            with patch.object(launcher, 'ROOT', source):
                work = launcher.make_workspace(Path(temp) / 'run')
            (work / 'results/evidence.json').write_text('{"rerun":true}')
            self.assertEqual(json.loads(original.read_text()), {'original': True})
            self.assertEqual((work / 'external').resolve(), source / 'external')
            self.assertFalse((work / 'results').is_symlink())

    def test_nested_or_existing_workspaces_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            source.mkdir()
            with patch.object(launcher, 'ROOT', source):
                with self.assertRaises(ValueError):
                    launcher.make_workspace(source / 'recursive')
                with self.assertRaises(FileExistsError):
                    launcher.make_workspace(Path(temp))

    def test_renamed_helper_import_works_outside_repository(self):
        code = ('import os, vlm_stove_state_readout as h; '
                'assert h.parse_object(\'```json\\n{"state":"unknown"}\\n```\')'
                '["state"] == "unknown"; print(os.getcwd())')
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'e2_validation'), PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd='/tmp', env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), ROOT)

    def test_relocated_provider_subprocess_keeps_json_protocol(self):
        # Provider mode uses no simulator and must emit only the protocol JSON.
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / 'state.json'
            payload.write_text('[{"objectId":"test-object","objectType":"Pan"}]')
            result = subprocess.run(
                [sys.executable, '-B', str(ROOT / 'e1_validation/kitchen_state_provider_pipeline.py'),
                 '--provider', str(payload)], cwd=temp, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['schema'], 'm6.observation.v1')
            self.assertEqual(data['objects'][0]['objectId'], 'test-object')


if __name__ == '__main__':
    unittest.main()
