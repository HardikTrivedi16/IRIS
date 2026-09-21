"""
Phase 8 §15 — property / edge-case testing beyond the FSSAI-specific
boundaries already covered in test_phase8_fssai_overlap_extended.py: empty
project facts, extra irrelevant project facts, repeated evaluation
stability, rule-ordering independence (synthetic), and confirming
irrelevant rules never leak into unrelated Requirements.
"""
import copy

from iris_engine.rules import EvaluationMode
from iris_engine.classification import evaluate_classification_group

NP = EvaluationMode.NON_PRODUCTION


def test_empty_project_facts_across_all_requirements(engine, dataset):
    for req_id in dataset.requirements:
        d = engine.evaluate_requirement("P", req_id, {}, NP)
        assert d["final_state"] in ("REQUIRES_INFORMATION",)
        assert d["final_state"] not in ("NOT_APPLICABLE",)


def test_extra_irrelevant_project_facts_do_not_change_outcome(engine):
    base_facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    extra_facts = dict(base_facts)
    extra_facts.update({
        "project.completely_unrelated_key": "some value",
        "project.industry": "PHARMA",  # irrelevant to REQ-0001's own rule
        "random_junk_key_12345": 999,
    })
    d1 = engine.evaluate_requirement("P", "REQ-0001", base_facts, NP, evaluated_at="fixed")
    d2 = engine.evaluate_requirement("P", "REQ-0001", extra_facts, NP, evaluated_at="fixed")
    assert d1 == d2


def test_repeated_evaluation_is_idempotent(engine):
    facts = {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 60000,
             "project.dairy_milk_solids_capacity": 1000}
    outcomes = [engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="fixed")
                for _ in range(20)]
    assert all(o == outcomes[0] for o in outcomes)


def test_irrelevant_rules_do_not_affect_unrelated_requirements(engine):
    # Facts relevant only to REQ-0004 (dairy/FSSAI) must not perturb
    # REQ-0001/REQ-0002/REQ-0003's own independent evaluations.
    shared_facts = {
        "project.likely_to_discharge_sewage_or_trade_effluent": True,
        "project.plant_located_in_air_pollution_control_area": False,
        "project.drug_schedule_classification": "GENERAL_SCHEDULE",
        "project.industry": "FOOD",
        "project.dairy_liquid_milk_capacity": 999999,   # wildly irrelevant/extreme
        "project.dairy_milk_solids_capacity": 999999,
    }
    minimal_facts = {
        "project.likely_to_discharge_sewage_or_trade_effluent": True,
        "project.plant_located_in_air_pollution_control_area": False,
        "project.drug_schedule_classification": "GENERAL_SCHEDULE",
    }
    for req_id in ("REQ-0001", "REQ-0002", "REQ-0003"):
        d_shared = engine.evaluate_requirement("P", req_id, shared_facts, NP, evaluated_at="fixed")
        d_minimal = engine.evaluate_requirement("P", req_id, minimal_facts, NP, evaluated_at="fixed")
        assert d_shared == d_minimal


def test_rule_ordering_independence_synthetic():
    # Synthetic classification group with two rules; confirm swapping the
    # order of classification_rule_ids in the Requirement produces an
    # identical combined_state/conflict_id (order must not matter).
    class _FakeDataset:
        def latest_rule_version_id(self, rule_id):
            for r in self.rules_index.get("rules", []):
                if r.get("rule_id") == rule_id:
                    return r.get("latest_rule_version_id")
            return None

    def make_ds(rule_order):
        ds = _FakeDataset()
        ds.conditions = {            "COND-A": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.a",
                       "operator": "==", "comparison_value": True, "child_condition_ids": []},
            "COND-B": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.b",
                       "operator": "==", "comparison_value": True, "child_condition_ids": []},
        }
        ds.rule_versions = {
            "RULE-A-V1": {"rule_version_id": "RULE-A-V1", "rule_id": "RULE-A", "status": "DRAFT",
                          "condition_expression_root_id": "COND-A",
                          "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"}},
            "RULE-B-V1": {"rule_version_id": "RULE-B-V1", "rule_id": "RULE-B", "status": "DRAFT",
                          "condition_expression_root_id": "COND-B",
                          "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"}},
        }
        ds.rules_index = {"rules": [
            {"rule_id": "RULE-A", "latest_rule_version_id": "RULE-A-V1"},
            {"rule_id": "RULE-B", "latest_rule_version_id": "RULE-B-V1"},
        ]}
        ds.requirements = {"REQ-SYNTH": {"evaluated_by_rule_id": None,
                                          "classification_rule_ids": rule_order}}
        ds.rule_conflict_register = {"conflicts": [
            {"conflict_id": "TEST-OVERLAP", "involved_rules": ["RULE-A", "RULE-B"],
             "combined_state_on_conflict": "REQUIRES_REVIEW", "review_reason": "TEST_CONFLICT"},
        ]}
        return ds

    facts = {"project.a": True, "project.b": True}
    ds_forward = make_ds(["RULE-A", "RULE-B"])
    ds_reversed = make_ds(["RULE-B", "RULE-A"])
    r_forward = evaluate_classification_group("REQ-SYNTH", ds_forward, facts, NP)
    r_reversed = evaluate_classification_group("REQ-SYNTH", ds_reversed, facts, NP)
    assert r_forward.combined_state == r_reversed.combined_state == "REQUIRES_REVIEW"
    assert r_forward.conflict_id == r_reversed.conflict_id == "TEST-OVERLAP"
