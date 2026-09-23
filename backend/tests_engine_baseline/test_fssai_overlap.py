from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION


def _facts(liquid=None, solids=None):
    # project.food_subsector: DAIRY — required by the FD-04 guard added
    # above RULE-0005/RULE-0006's condition roots (COND-0037/COND-0038) so
    # a non-dairy project can never accidentally evaluate against dairy
    # capacity bands. These tests are specifically about dairy behavior.
    facts = {"project.industry": "FOOD", "project.food_subsector": "DAIRY"}
    if liquid is not None:
        facts["project.dairy_liquid_milk_capacity"] = liquid
    if solids is not None:
        facts["project.dairy_milk_solids_capacity"] = solids
    return facts


def test_case_60000_1000_both_true_requires_review(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(60000, 1000), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["classification"]["combined_state"] == "REQUIRES_REVIEW"
    assert d["classification"]["conflict_id"] == "OVERLAP-0001"
    assert d["final_state"] == "REQUIRES_REVIEW"


def test_case_40000_3000_both_true_requires_review(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(40000, 3000), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["classification"]["combined_state"] == "REQUIRES_REVIEW"
    assert d["classification"]["conflict_id"] == "OVERLAP-0001"
    assert d["final_state"] == "REQUIRES_REVIEW"


def test_case_40000_1000_central_false_state_true(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(40000, 1000), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["classification"]["combined_state"] == "APPLICABLE"
    assert d["final_state"] == "APPLICABLE"


def test_case_50000_2500_central_false_state_true(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(50000, 2500), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["classification"]["combined_state"] == "APPLICABLE"
    assert d["final_state"] == "APPLICABLE"


def test_case_missing_capacity_requires_information(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(None, None), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "REQUIRES_INFORMATION"
    assert d["classification"]["rule_results"]["RULE-0006"] == "REQUIRES_INFORMATION"
    assert d["classification"]["combined_state"] == "REQUIRES_INFORMATION"
    assert d["final_state"] == "REQUIRES_INFORMATION"


def test_no_invented_precedence_in_conflict_text(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(60000, 1000), NP)
    text = d["reason_text"].lower()
    # No wording asserting one authority overrides the other:
    assert "takes precedence" not in text
    assert "overrides" not in text
