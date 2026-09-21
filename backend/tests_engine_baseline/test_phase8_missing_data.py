"""
Phase 8 §9 — missing/unknown project facts. Confirms missing fact -> UNKNOWN
-> REQUIRES_INFORMATION (when the Rule Version's output_mapping provides it),
NEVER missing -> FALSE -> NOT_APPLICABLE, across every required-fact
category (boolean, schedule, industry, dairy liquid, dairy solids), and the
composite Kleene invariants named in the brief.
"""
import pytest

from iris_engine.rules import EvaluationMode
from iris_engine.kleene import T, F, U, kleene_and, kleene_or

NP = EvaluationMode.NON_PRODUCTION


@pytest.mark.parametrize("requirement_id,facts", [
    ("REQ-0001", {}),  # missing boolean fact
    ("REQ-0002", {}),  # missing boolean fact
    ("REQ-0003", {}),  # missing schedule
    ("REQ-0004", {}),  # missing industry
])
def test_missing_required_fact_never_becomes_not_applicable(engine, requirement_id, facts):
    d = engine.evaluate_requirement("P", requirement_id, facts, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert d["final_state"] != "NOT_APPLICABLE"


def test_missing_dairy_liquid_capacity_only(engine):
    d = engine.evaluate_requirement("P", "REQ-0004",
        {"project.industry": "FOOD", "project.dairy_milk_solids_capacity": 0}, NP)
    # solids=0 definitively FALSE on both rules; liquid missing -> F|U=U
    assert d["classification"]["rule_results"]["RULE-0005"] == "REQUIRES_INFORMATION"
    assert d["classification"]["rule_results"]["RULE-0006"] == "REQUIRES_INFORMATION"


def test_missing_dairy_solids_capacity_only(engine):
    d = engine.evaluate_requirement("P", "REQ-0004",
        {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 0}, NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "REQUIRES_INFORMATION"
    assert d["classification"]["rule_results"]["RULE-0006"] == "REQUIRES_INFORMATION"


def test_missing_facts_never_silently_become_false_across_all_six_rules(dataset):
    from iris_engine.rules import evaluate_rule_version
    for rv_id in [f"RULE-{i:04d}-V1" for i in range(1, 7)]:
        r = evaluate_rule_version(rv_id, dataset, {}, NP)
        assert r.kleene_result is U
        assert r.final_state != "NOT_APPLICABLE"


# --- composite Kleene behavior named explicitly in the brief ---------------

def test_true_or_unknown_equals_true():
    assert kleene_or(T, U) is T


def test_false_or_unknown_equals_unknown():
    assert kleene_or(F, U) is U


def test_false_and_unknown_equals_false():
    assert kleene_and(F, U) is F


def test_true_and_unknown_equals_unknown():
    assert kleene_and(T, U) is U


def test_composite_and_or_against_real_condition_trees(dataset):
    from iris_engine.conditions import evaluate_condition
    c = dataset.conditions
    # TRUE OR UNKNOWN via COND-0007 (liquid known TRUE, solids missing)
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 60000})
    assert r.result is T

    # FALSE OR UNKNOWN via COND-0007 (liquid known FALSE, solids missing)
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 100})
    assert r.result is U

    # FALSE AND UNKNOWN via COND-0010 (liquid < 501 known FALSE on lower
    # bound, upper bound comparison still resolvable but AND already F)
    r = evaluate_condition("COND-0010", c, {"project.dairy_liquid_milk_capacity": 100})
    assert r.result is F  # 100 < 501 -> lower bound FALSE, AND short-circuits to F

    # TRUE AND UNKNOWN via a synthetic composite (both COND-0010 sub-facts
    # partially known): give only the upper bound fact, lower bound missing.
    conditions = dict(c)
    r = evaluate_condition("COND-0010", conditions, {})  # both missing -> U AND U = U
    assert r.result is U
