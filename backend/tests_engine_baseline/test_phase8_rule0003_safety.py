"""
Phase 8 §6 — RULE-0003/REQ-0003 safety-critical test: NONE, SCHEDULE_C_OR_C1,
SCHEDULE_X_ONLY, SCHEDULE_C_OR_C1_AND_X, and missing schedule, through the
full engine. Confirms Schedule C/C1/X can NEVER become NOT_APPLICABLE, and
that no alternative licence pathway is inferred.

REWRITTEN 2026-09-23 for the Pharma tranche's ENUM reshape and REQ-0003
coarse-gate + classification_rule_ids restructuring (see
regulatory-data/registers/rule_review_register.yaml RULE-REV-0002). Prior
to this pass, `drug_schedule_classification` was a free-form NOT_IN-list
string and Schedule C/C1/X dead-ended at REQUIRES_REVIEW; that dead-end no
longer exists — PH-02/PH-03 give a real, positive APPLICABLE answer for
those schedules now, surfaced through this Requirement's classification.
"""
import pytest

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION

_GATE = {
    "project.manufactures_drugs_for_sale_or_distribution": True,
    "project.pharma_activity_type": "FORMULATIONS",
}

EXPECTED = {
    "NONE": "APPLICABLE",
    "SCHEDULE_C_OR_C1": "APPLICABLE",
    "SCHEDULE_X_ONLY": "APPLICABLE",
    "SCHEDULE_C_OR_C1_AND_X": "APPLICABLE",
}


def _facts(schedule):
    f = dict(_GATE)
    f["project.drug_schedule_classification"] = schedule
    return f


@pytest.mark.parametrize("schedule,expected_state", list(EXPECTED.items()))
def test_rule_0003_required_states(engine, schedule, expected_state):
    d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
    assert d["final_state"] == expected_state
    assert d["final_state"] != "NOT_APPLICABLE"


def test_rule_0003_missing_schedule(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", dict(_GATE), NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert d["final_state"] != "NOT_APPLICABLE"


@pytest.mark.parametrize(
    "schedule", ["SCHEDULE_C_OR_C1", "SCHEDULE_X_ONLY", "SCHEDULE_C_OR_C1_AND_X"]
)
def test_schedule_c_c1_x_never_not_applicable_across_repeated_runs(engine, schedule):
    # run several times to rule out any nondeterminism
    for _ in range(5):
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        assert d["final_state"] == "APPLICABLE"
        assert d["final_state"] != "NOT_APPLICABLE"


def test_no_alternative_pathway_inferred_in_reason_text(engine):
    # The engine must not invent a Rule 70 / Form 25 pathway (Task 2's
    # unverified framing, explicitly not adopted per REQ-0003's requirement_notes).
    for schedule in ("SCHEDULE_C_OR_C1", "SCHEDULE_X_ONLY", "SCHEDULE_C_OR_C1_AND_X"):
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        text = d["reason_text"].lower()
        assert "rule 70" not in text
        assert "form 25\"" not in text  # RULE-0017's own Form 25 (NONE) text is fine; only
                                         # a bare Task-2-style "Rule 70...Form 25" claim is banned


def test_rule_0003_unrecognized_schedule_value_never_falsely_pins_a_specific_pathway(engine):
    # An unrecognized/out-of-domain schedule value no longer falls through
    # to "treated as GENERAL/NONE" (the old NOT_IN-over-3-values semantics)
    # -- the ENUM leaves (COND-0048/0050/0052/0053) are exact "==" matches,
    # so none of PH-01/02/03 fire for a garbage value. The coarse gate
    # (RULE-0003) itself doesn't test schedule at all, so the Requirement's
    # top-level answer still reports APPLICABLE (some pathway exists), but
    # the classification breakdown must show NONE of the three specific
    # pathways firing -- i.e. the engine must not silently pin a pathway
    # for a value it does not recognize.
    d = engine.evaluate_requirement(
        "P", "REQ-0003", _facts("SOME_OTHER_SCHEDULE_VALUE"), NP
    )
    assert d["final_state"] == "APPLICABLE"
    for rule_id in ("RULE-0017", "RULE-0018", "RULE-0019"):
        assert d["classification"]["rule_results"][rule_id] == "NOT_APPLICABLE"
