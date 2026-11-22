from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_attribute_native_v2 import build_protocol,load_cases


class ConfigurableAttributeTests(unittest.TestCase):
    def test_requested_cases_define_complete_matrix(self):
        requested=['attribute_FloorPlan5_01','attribute_FloorPlan8_07']
        protocol=build_protocol(requested)
        self.assertEqual([x['case_id'] for x in protocol['cases']],requested)
        self.assertEqual(protocol['expected'],24)
        self.assertEqual(len({(x['case_id'],x['condition'],x['arm']) for x in protocol['assignments']}),24)

    def test_duplicate_unknown_or_relation_rejected(self):
        for cases in ([],['attribute_FloorPlan5_01']*2,['does_not_exist'],['relation_FloorPlan6_02']):
            with self.subTest(cases=cases),self.assertRaises(ValueError): load_cases(cases)

if __name__=='__main__': unittest.main()
