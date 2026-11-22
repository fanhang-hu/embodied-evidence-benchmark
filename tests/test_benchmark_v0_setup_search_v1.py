import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_setup_search_v1 import attempt,case_relevant

CASE={'scene':'FloorPlan12','family':'relation','pan_id':'pan','knob_id':'knob','burner_id':'burner'}


def snapshot(held=False,other=False):
    objects=[{'objectId':'knob','objectType':'StoveKnob','isToggled':False,'controlledObjects':['burner']},
             {'objectId':'pan','objectType':'Pan','parentReceptacles':None if held else ['burner']}]
    if other: objects.append({'objectId':'pot','objectType':'Pot','parentReceptacles':['burner']})
    return {'objects':objects}


class Controller:
    def __init__(self): self.last_event=type('E',(),{'metadata':{'lastActionSuccess':True}})()
    def reset(self,**kwargs): pass


class Driver:
    extra=False
    def __init__(self,controller,case): self.calls=0
    def snapshot(self):
        self.calls+=1
        return snapshot(held=self.calls>1,other=self.extra and self.calls>1)
    def navigate(self,target): return {'success':True,'receipts':[]}
    def execute(self,action,role): return {'request':action,'success':True,'last_action':action['action']}


def fake_step(controller,action,log):
    r={'request':action,'success':True,'last_action':action['action']}; log.append(r); return r


class SetupSearchTests(unittest.TestCase):
    def test_truth_collects_all_cookware(self):
        truth=case_relevant(snapshot(held=True,other=True),CASE)
        self.assertEqual(truth['cookware_on_target'],['pot'])
        self.assertEqual(truth['controlled'],['burner'])

    def run_attempt(self,extra):
        Driver.extra=extra; row={}; persists=[]
        with patch('benchmark_v0_setup_search_v1.objects',return_value=[{'objectType':'StoveKnob','isToggled':False}]), \
             patch('benchmark_v0_setup_search_v1.step',side_effect=fake_step), \
             patch('benchmark_v0_setup_search_v1.approach',return_value=True), \
             patch('benchmark_v0_setup_search_v1.NativeDriver',Driver):
            attempt(Controller(),CASE,row,lambda: persists.append(True))
        return row,persists

    def test_valid_setup_and_unforced_drift(self):
        row,persists=self.run_attempt(False)
        self.assertTrue(row['setup_receipts'][0]['request']['forceAction'])
        self.assertFalse(row['drift_receipt']['request']['forceAction'])
        self.assertEqual(row['unsafe_truth']['cookware_on_target'],[])
        self.assertGreaterEqual(len(persists),6)

    def test_other_cookware_makes_unsafe_setup_infeasible(self):
        with self.assertRaisesRegex(RuntimeError,'unsafe truth'):
            self.run_attempt(True)


if __name__=='__main__': unittest.main()
