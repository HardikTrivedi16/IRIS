"""
Phase 9 Section 6 — the FSSAI Central/State overlap must remain explainable
as an unresolved conflict: both participating rules, their individual
results, the conflict ID, conflict status, and the absence of authoritative
precedence -- for both overlap fact patterns from Phase 8's test suite.
"""
from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION


def _facts(liquid, solids):
    return {"project.industry": "FOOD", "project.food_subsector": "DAIRY",
            "project.dairy_liquid_milk_capacity": liquid,
            "project.dairy_milk_solids_capacity": solids}


def test_overlap_60000_1000_is_explainable_and_unresolved(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(60000, 1000), NP)
    assert d["final_state"] == "REQUIRES_REVIEW"
    assert d["explanation"]["conflict_id"] == "OVERLAP-0001"
    assert d["explanation"]["classification"]["rule_results"] == {
        "RULE-0005": "APPLICABLE", "RULE-0006": "APPLICABLE",
    }
    # Both participating rules' own condition trees are individually visible.
    trees = d["explanation"]["classification_condition_trees"]
    assert set(trees.keys()) == {"RULE-0005", "RULE-0006"}
    assert trees["RULE-0005"]["result"] == "TRUE"
    assert trees["RULE-0006"]["result"] == "TRUE"


def test_overlap_40000_3000_is_explainable_and_unresolved(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(40000, 3000), NP)
    assert d["final_state"] == "REQUIRES_REVIEW"
    assert d["explanation"]["conflict_id"] == "OVERLAP-0001"
    assert d["explanation"]["classification"]["rule_results"] == {
        "RULE-0005": "APPLICABLE", "RULE-0006": "APPLICABLE",
    }


def test_no_precedence_is_ever_asserted_in_the_narrative(engine):
    for liquid, solids in [(60000, 1000), (40000, 3000)]:
        d = engine.evaluate_requirement("P", "REQ-0004", _facts(liquid, solids), NP)
        text = d["explanation"]["narrative"].lower()
        assert "takes precedence" not in text
        assert "overrides" not in text
        assert "wins" not in text


def test_non_overlap_cases_remain_applicable_and_explainable(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(40000, 1000), NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["explanation"]["conflict_id"] is None
    assert d["explanation"]["classification"]["rule_results"] == {
        "RULE-0005": "NOT_APPLICABLE", "RULE-0006": "APPLICABLE",
    }


def test_missing_capacity_facts_requires_information_with_both_rules_shown(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(None, None), NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert d["explanation"]["classification"]["rule_results"] == {
        "RULE-0005": "REQUIRES_INFORMATION", "RULE-0006": "REQUIRES_INFORMATION",
    }
    trees = d["explanation"]["classification_condition_trees"]
    assert trees["RULE-0005"]["result"] == "UNKNOWN"
    assert trees["RULE-0006"]["result"] == "UNKNOWN"
