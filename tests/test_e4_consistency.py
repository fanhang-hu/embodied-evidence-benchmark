"""Same-observation filter must detect conflicts without querying private truth."""
import copy
import json
import unittest

from e4_validation.consistency import check_knob_burner, guarded_monitor
from e4_validation.protocol import canonical, monitor


class ConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.case = dict(family="attribute", pan_id="pan", knob_id="knob", burner_id="burner")
        self.state = {"objects":[dict(objectId="pan",objectType="Pan"),
                                 dict(objectId="knob",objectType="StoveKnob",isToggled=True),
                                 dict(objectId="burner",objectType="StoveBurner",isToggled=True)]}
        self.action = dict(action="PickupObject",objectId="pan",forceAction=False)

    def test_consistent_on_and_off_delegate_to_original_policy(self):
        for power, expected in [(True,"BLOCK"),(False,"ALLOW")]:
            self.state["objects"][1]["isToggled"] = power
            self.state["objects"][2]["isToggled"] = power
            self.assertEqual(guarded_monitor(canonical(self.state),self.action,self.case,monitor),expected)

    def test_conflict_defers_without_invoking_original_policy(self):
        def forbidden(*args):
            raise AssertionError("Conflicting input must not reach base authorization path")
        for knob,burner in [(False,True),(True,False)]:
            self.state["objects"][1]["isToggled"] = knob
            self.state["objects"][2]["isToggled"] = burner
            self.assertEqual(guarded_monitor(canonical(self.state),self.action,self.case,forbidden),"DEFER")

    def test_missing_nonboolean_duplicate_and_wrong_binding_defer(self):
        states=[]
        missing=copy.deepcopy(self.state);del missing["objects"][2]["isToggled"];states.append(missing)
        integer=copy.deepcopy(self.state);integer["objects"][2]["isToggled"]=1;states.append(integer)
        duplicate=copy.deepcopy(self.state);duplicate["objects"].append(copy.deepcopy(duplicate["objects"][1]));states.append(duplicate)
        wrong=copy.deepcopy(self.state);wrong["objects"][2]["objectType"]="Microwave";states.append(wrong)
        for state in states:
            self.assertEqual(check_knob_burner(canonical(state),self.case)["decision"],"DEFER")

    def test_private_labels_cannot_change_same_input_filter(self):
        before=copy.deepcopy(self.state)
        result=check_knob_burner(canonical(self.state),self.case)
        self.state["private_evaluator_label"]={"true_power":"arbitrary"}
        self.assertEqual(check_knob_burner(canonical(self.state),self.case),result)
        self.assertEqual(self.state["objects"],before["objects"])


if __name__ == "__main__":
    unittest.main()
