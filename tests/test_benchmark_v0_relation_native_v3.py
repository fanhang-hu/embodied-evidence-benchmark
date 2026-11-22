from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_relation_native_v3 import build_protocol,contract_satisfied,load_cases


class RelationNativeTests(unittest.TestCase):
    def test_matrix_includes_same_source(self):
        p=build_protocol(['relation_FloorPlan6_02','relation_FloorPlan8_06'])
        self.assertEqual(p['expected'],30)
        self.assertEqual(len({(a['case_id'],a['condition'],a['arm']) for a in p['assignments']}),30)
        self.assertEqual(sum(a['arm']=='same_source_fresh' for a in p['assignments']),6)

    def test_invalid_cases_rejected(self):
        for cases in ([],['relation_FloorPlan6_02']*2,['attribute_FloorPlan6_03'],['no_such_case']):
            with self.subTest(cases=cases),self.assertRaises(ValueError): load_cases(cases)

    def test_contract_considers_other_cookware(self):
        case={'burner_id':'burner'}
        state={'objects':[{'objectType':'Pan','parentReceptacles':None},{'objectType':'Pot','parentReceptacles':['burner']}]}
        self.assertTrue(contract_satisfied(state,case))
        state['objects'][1]['parentReceptacles']=[]
        self.assertFalse(contract_satisfied(state,case))

if __name__=='__main__': unittest.main()
