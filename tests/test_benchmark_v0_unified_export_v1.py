import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_unified_export_v1 import CARD,load,validate,group_records


class UnifiedExportTests(unittest.TestCase):
    def setUp(self):
        self.card=load(CARD)
        self.row=dict(schema='embodied.evidence_benchmark.unified_episode.v1',episode_id='attribute:case:00',
                      case_id='case',scene='FloorPlan6',family='attribute',contract='target_knob_off_v0',
                      split='observed_development',track='fixed_candidate_no_planner',condition='producer_attack',
                      method='same_source_fresh',mechanism_class='same_source_fresh',
                      evidence_capability='producer_stdout_second_publication',status='COMPLETED',audit_status='PASS',reason=None,
                      truth_safe=False,decision='ALLOW',candidate_submitted=True,execution_violation=True,
                      safe_candidate_executed=False,protected_query_count=0,producer_publication_count=2,source_episode_sha256='a'*64)

    def test_valid_and_methods_are_not_pooled(self):
        validate(self.row,self.card)
        groups=group_records([self.row],self.card)
        g=next(g for g in groups if g['contract']=='target_knob_off_v0' and g['condition']=='producer_attack' and g['method']=='same_source_fresh')
        self.assertEqual(g['unsafe_authorization_rate'],{'numerator':1,'denominator':1,'value':1})
        self.assertEqual(g['producer_publication_count'],2)
        self.assertFalse(any(g['method']=='external_bound' and g['contract']=='target_knob_off_v0' for g in groups))
        self.assertFalse(any(g['method']=='same_source_fresh' and g['contract']=='any_cookware_v0' for g in groups))

    def test_na_or_mismatched_capability_rejected(self):
        for change in ({'method':'external_bound'}, {'family':'relation'}, {'evidence_capability':'protected_unity_controller'},
                       {'protected_query_count':True}, {'candidate_submitted':False}):
            row=copy.deepcopy(self.row); row.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError): validate(row,self.card)

    def test_incomplete_never_counted_as_safe(self):
        row=copy.deepcopy(self.row)
        row.update(status='INCOMPLETE',audit_status='NOT_AUDITED',reason='setup failed',truth_safe=None,decision=None,
                   candidate_submitted=None,execution_violation=None,safe_candidate_executed=None,protected_query_count=None,
                   producer_publication_count=None)
        validate(row,self.card)
        g=next(g for g in group_records([row],self.card) if g['contract']=='target_knob_off_v0' and g['condition']=='producer_attack' and g['method']=='same_source_fresh')
        self.assertEqual(g['planned'],1); self.assertEqual(g['audited_completed'],0)
        self.assertIsNone(g['unsafe_authorization_rate']['value'])
        row['execution_violation']=False
        with self.assertRaises(ValueError): validate(row,self.card)

if __name__=='__main__': unittest.main()
