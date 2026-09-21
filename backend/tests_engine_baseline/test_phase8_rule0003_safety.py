"""
Phase 8 §6 — RULE-0003 safety-critical test: GENERAL_SCHEDULE, SCHEDULE_C,
SCHEDULE_C1, SCHEDULE_X, and missing schedule, through the full engine
(REQ-0003). Confirms Schedule C/C1/X can NEVER become NOT_APPLICABLE, and
that no alternative licence pathway is inferred.
"""
import pytest

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION

EXPECTED = {
    "GENERAL_SCHEDULE": "APPLICABLE",
    "SCHEDULE_C": "REQUIRES_REVIEW",
    "SCHEDULE_C1": "REQUIRES_REVIEW",
    "SCHEDULE_X": "REQUIRES_REVIEW",
}


@pytest.mark.parametrize("schedule,expected_state", list(EXPECTED.items()))
def test_rule_0003_required_states(engine, schedule, expected_state):
    d = engine.evaluate_requirement("P", "REQ-0003",
        {"project.drug_schedule_classification": schedule}, NP)
    assert d["final_state"] == expected_state
    assert d["final_state"] != "NOT_APPLICABLE"


def test_rule_0003_missing_schedule(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert d["final_state"] != "NOT_APPLICABLE"


@pytest.mark.parametrize("schedule", ["SCHEDULE_C", "SCHEDULE_C1", "SCHEDULE_X"])
def test_schedule_never_not_applicable_across_repeated_runs(engine, schedule):
    # run several times to rule out any nondeterminism
    for _ in range(5):
        d = engine.evaluate_requirement("P", "REQ-0003",
            {"project.drug_schedule_classification": schedule}, NP)
        assert d["final_state"] == "REQUIRES_REVIEW"


def test_no_alternative_pathway_inferred_in_reason_text(engine):
    # The engine must not invent a Rule 70 / Form 25 pathway (Task 2's
    # unverified framing, explicitly not adopted per REQ-0003's requirement_notes).
    for schedule in ("SCHEDULE_C", "SCHEDULE_C1", "SCHEDULE_X"):
        d = engine.evaluate_requirement("P", "REQ-0003",
            {"project.drug_schedule_classification": schedule}, NP)
        text = d["reason_text"].lower()
        assert "rule 70" not in text
        assert "form 25" not in text


def test_rule_0003_arbitrary_unrecognized_schedule_value_treated_as_general(engine):
    # Any value NOT in the excluded set (per COND-0003's NOT_IN operator)
    # resolves the same as GENERAL_SCHEDULE -- this is the condition's own
    # documented semantics (SET_MEMBERSHIP / NOT_IN over exactly three
    # excluded values), not an engine invention.
    d = engine.evaluate_requirement("P", "REQ-0003",
        {"project.drug_schedule_classification": "SOME_OTHER_SCHEDULE_VALUE"}, NP)
    assert d["final_state"] == "APPLICABLE"
