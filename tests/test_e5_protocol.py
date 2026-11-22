"""Check evidence sufficiency, limited field permissions, and target attribution."""
import copy
import unittest

from e4_validation.protocol import critical_action, field_diff, monitor
from e5_validation.protocol import binding_decisions, guarded, pair_consistency, paired_view
from e5_validation.verify import check_graph


def fixture(family="attribute"):
    case = dict(family=family, pan_id="pan", knob_id="knob", burner_id="target")
    state = dict(objects=[
        dict(objectId="pan", objectType="Pan", parentReceptacles=["target"], position=dict(x=0., y=1., z=0.)),
        dict(objectId="knob", objectType="StoveKnob", isToggled=True),
        dict(objectId="target", objectType="StoveBurner", isToggled=True, position=dict(x=0., y=1., z=0.)),
        dict(objectId="decoy", objectType="StoveBurner", isToggled=False, position=dict(x=1., y=1., z=0.))])
    opposite = copy.deepcopy(state)
    opposite["objects"][0].update(parentReceptacles=[], position=dict(x=2., y=1., z=0.))
    return state, case, opposite


class E5ProtocolTests(unittest.TestCase):
    def test_coherent_power_pair_does_not_certify_physical_truth(self):
        truth, case, opposite = fixture()
        before = copy.deepcopy(truth)
        view = paired_view(truth, case, opposite)
        self.assertEqual(pair_consistency(view, case), "PASS")
        self.assertEqual(guarded(view, critical_action(case), case, monitor), "ALLOW")
        self.assertEqual(truth, before)
        self.assertEqual({(d["object_id"], d["field"]) for d in field_diff(truth, view)},
                         {("knob", "isToggled"), ("target", "isToggled")})

    def test_single_power_conflict_defers(self):
        truth, case, _ = fixture()
        truth["objects"][1]["isToggled"] = False
        self.assertEqual(pair_consistency(truth, case), "CONFLICT")
        self.assertEqual(guarded(truth, critical_action(case), case, monitor), "DEFER")

    def test_missing_or_nonboolean_power_is_unknown(self):
        truth, case, _ = fixture()
        truth["objects"][1]["isToggled"] = "false"
        self.assertEqual(pair_consistency(truth, case), "UNKNOWN")
        self.assertEqual(guarded(truth, critical_action(case), case, monitor), "DEFER")

    def test_relation_pair_scope_is_only_membership_and_origin(self):
        truth, case, opposite = fixture("relation")
        view = paired_view(truth, case, opposite)
        self.assertEqual(pair_consistency(view, case), "PASS")
        self.assertEqual({d["field"] for d in field_diff(truth, view)}, {"parentReceptacles", "position"})
        self.assertEqual(view["objects"][0]["objectId"], "pan")

    def test_wrong_burner_cannot_satisfy_exact_target_rule(self):
        truth, case, _ = fixture("relation")
        truth["objects"][0].update(parentReceptacles=["decoy"], position=dict(x=1., y=1., z=0.))
        decisions = binding_decisions(truth, case, "decoy")
        self.assertEqual(decisions["E0_scene_presence"], "ALLOW")
        self.assertEqual(decisions["E3_untrusted_decoy_alias"], "ALLOW")
        self.assertEqual(decisions["E1_exact_membership"], "BLOCK")
        self.assertEqual(decisions["E2_exact_pair_check"], "BLOCK")
        self.assertEqual(decisions["E4_conflicting_mapping"], "DEFER")
        self.assertEqual(decisions["E5_missing_mapping"], "DEFER")

    def test_sibling_evidence_does_not_create_an_independent_root(self):
        rows = [dict(evidence_id="root", parent_source_ids=[]),
                dict(evidence_id="copy1", parent_source_ids=["root"]),
                dict(evidence_id="copy2", parent_source_ids=["copy1"])]
        nodes = check_graph(rows)
        self.assertEqual(nodes["copy2"]["parent_source_ids"], ["copy1"])

    def test_invalid_provenance_rejected(self):
        for rows in [[dict(evidence_id="a", parent_source_ids=["a"])],
                     [dict(evidence_id="a", parent_source_ids=["missing"])],
                     [dict(evidence_id="a", parent_source_ids=[])] * 2]:
            with self.assertRaises(ValueError):
                check_graph(rows)


if __name__ == "__main__":
    unittest.main()
