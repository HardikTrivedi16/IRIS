"""
Phase 9 Section 10 — reproducibility: given the same engine version, Rule
Version(s), input fact snapshot, evaluation mode, and regulatory-data
version, the semantic Decision must be identical. Non-semantic fields
(timestamps, decision_id) are ignored in the comparison.
"""
from iris_engine.rules import EvaluationMode
from iris_engine.reproducibility import semantically_equal, semantic_diff

NP = EvaluationMode.NON_PRODUCTION


def _fssai_facts():
    return {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 60000,
            "project.dairy_milk_solids_capacity": 1000}


def test_repeated_evaluation_is_byte_identical_with_fixed_timestamp(engine):
    facts = _fssai_facts()
    results = [
        engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="fixed")
        for _ in range(10)
    ]
    assert all(r == results[0] for r in results)


def test_semantically_equal_ignores_only_timestamp_and_id(engine):
    facts = _fssai_facts()
    d1 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="2026-01-01T00:00:00Z")
    d2 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="2099-12-31T23:59:59Z")
    assert d1 != d2  # different evaluated_at, so not byte-identical
    assert semantically_equal(d1, d2)  # but semantically the same decision
    assert semantic_diff(d1, d2) == {}


def test_semantically_equal_detects_a_real_difference(engine):
    d1 = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP
    )
    d2 = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": False}, NP
    )
    assert not semantically_equal(d1, d2)
    diff = semantic_diff(d1, d2)
    assert "final_state" in diff


def test_decision_id_is_a_reproducibility_fingerprint(engine):
    facts = _fssai_facts()
    d1 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="a")
    d2 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="b")
    assert d1["decision_id"] == d2["decision_id"]

    other_facts = dict(facts, **{"project.dairy_milk_solids_capacity": 999})
    d3 = engine.evaluate_requirement("P", "REQ-0004", other_facts, NP, evaluated_at="a")
    assert d3["decision_id"] != d1["decision_id"]


def test_condition_results_missing_facts_review_and_dependency_all_reproduce(engine):
    facts = {"project.drug_schedule_classification": "SCHEDULE_C"}
    d1 = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    d2 = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    exp1, exp2 = d1["explanation"], d2["explanation"]
    assert exp1["condition_evaluation_tree"] == exp2["condition_evaluation_tree"]
    assert exp1["missing_facts"] == exp2["missing_facts"]
    assert exp1["review_reason"] == exp2["review_reason"]
    assert exp1["dependency_result"] == exp2["dependency_result"]
    assert exp1["provenance"] == exp2["provenance"]
