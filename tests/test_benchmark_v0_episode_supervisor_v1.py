import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_episode_supervisor_v1 import monitor, observe, read_progress


def entry(i=0):
    return dict(assignment_id=f'case:{i:02d}', case_id='case', scene='FloorPlan6', index=i,
                condition='producer_attack', guard='public_reference', status='PLANNED',
                audit_status='NOT_YET_VERIFIED')


class EpisodeSupervisorTests(unittest.TestCase):
    def test_true_hang_targets_observed_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); case = root / 'case'; case.mkdir()
            rows = [entry(0), entry(1)]; snapshots = []
            code = ('import json,sys,time; from pathlib import Path; '
                    'Path(sys.argv[1]).write_text(json.dumps({"attempted":1,"completed":0})); time.sleep(30)')
            result = monitor([sys.executable, '-c', code, str(case / 'status.json')], case, rows, root / 'log',
                             episode_timeout=0.2, case_timeout=5, poll_seconds=0.01,
                             persist=lambda: snapshots.append([r['status'] for r in rows]))
            self.assertEqual((result['status'], result['timeout_index']), ('EPISODE_TIMEOUT', 0))
            self.assertEqual([r['status'] for r in rows], ['TIMEOUT_OBSERVED', 'PLANNED'])
            self.assertTrue(any(s[0] == 'RUNNING_OBSERVED' for s in snapshots))

    def test_complete_record_even_if_start_not_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); private = root / 'private'; private.mkdir()
            rows = [entry()]
            (root / 'status.json').write_text(json.dumps({'attempted': 1, 'completed': 1}))
            (private / '00_episode.json').write_text(json.dumps({'index': 0, 'case_id': 'case', 'condition': 'producer_attack',
                                                                 'arm': 'public_reference', 'status': 'COMPLETED'}))
            changed, progress = observe(root, rows, 123)
            self.assertTrue(changed); self.assertEqual(progress, (1, 1))
            self.assertEqual(rows[0]['status'], 'COMPLETED_RECORDED')
            self.assertNotIn('start_observed_monotonic_ns', rows[0])
            self.assertEqual(rows[0]['audit_status'], 'NOT_YET_VERIFIED')

    def test_unreadable_progress_is_unknown_not_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'status.json').write_text('{')
            self.assertIsNone(read_progress(root / 'status.json', 1))
            rows = [entry()]
            result = monitor([sys.executable, '-c', 'import time; time.sleep(30)'], root, rows, root / 'log',
                             episode_timeout=0.05, case_timeout=0.15, poll_seconds=0.01, persist=lambda: None)
            self.assertEqual(result['status'], 'CASE_TIMEOUT')
            self.assertEqual(rows[0]['status'], 'PLANNED')

    def test_bad_episode_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'private').mkdir()
            (root / 'private/00_episode.json').write_text(json.dumps({'index': 0, 'case_id': 'wrong'}))
            with self.assertRaises(ValueError): observe(root, [entry()], 1)


if __name__ == '__main__': unittest.main()
