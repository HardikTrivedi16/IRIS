"""
Phase 9 Section 2, Section 4, Section 13 — the full per-Requirement
Explanation block: all required keys present, UNKNOWN/REQUIRES_REVIEW/
REQUIRES_INFORMATION/BLOCKED_DRAFT_NOT_PRODUCTION never collapsed into one
another, review/conflict reasons surfaced, blocked evaluations explainable.
"""
from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

REQUIRED_EXPLANATION_FIELDS = {
    "requirement_id", "rule_id", "rule_version_id", "rule_version_status",
    "evaluation_mode", "final_state", "narrative", "condition_evaluation_tree",
    "input_facts_used", "missing_facts", "declared_required_facts",
    "rule_output_mapping", "review_reason", "conflict_id", "classification",
    "classification_condition_trees", "classification_rule_output_mappings",
    "dependency_result", "provenance", "engine_version",
}


def test_explanation_has_every_required_field_applicable_case(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP
    )
    assert REQUIRED_EXPLANATION_FIELDS.issubset(d["explanation"].keys())


def test_explanation_has_every_required_field_blocked_draft_case(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {}, PROD)
    assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    assert REQUIRED_EXPLANATION_FIELDS.issubset(d["explanation"].keys())
    assert d["explanation"]["narrative"]
    assert d["explanation"]["rule_version_status"] == "DRAFT"
    assert d["explanation"]["evaluation_mode"] == "PRODUCTION"


def test_unknown_state_shows_exactly_which_facts_are_missing(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert "project.likely_to_discharge_sewage_or_trade_effluent" in d["explanation"]["narrative"]
    assert d["explanation"]["missing_facts"] == ["project.holds_prior_environmental_clearance", "project.is_white_category_industrial_plant", "project.likely_to_discharge_sewage_or_trade_effluent"]


def test_requires_review_shows_reason_and_no_invented_precedence(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0004",
        {"project.industry": "FOOD", "project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 60000,
         "project.dairy_milk_solids_capacity": 1000},
        NP,
    )
    assert d["final_state"] == "REQUIRES_REVIEW"
    exp = d["explanation"]
    assert exp["conflict_id"] == "OVERLAP-0001"
    assert "REQUIRES_REVIEW" in exp["narrative"]
    text = exp["narrative"].lower()
    assert "takes precedence" not in text and "overrides" not in text


def test_states_are_never_collapsed_into_each_other(engine):
    seen_states = set()
    cases = [
        ("REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, NP),
        ("REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": False}, NP),
        ("REQ-0001", {}, NP),
        ("REQ-0004", {"project.industry": "FOOD", "project.food_subsector": "DAIRY",
                       "project.dairy_liquid_milk_capacity": 60000,
                       "project.dairy_milk_solids_capacity": 1000}, NP),
        ("REQ-0001", {}, PROD),
    ]
    for req_id, facts, mode in cases:
        d = engine.evaluate_requirement("P", req_id, facts, mode)
        seen_states.add(d["final_state"])
    assert seen_states == {
        "APPLICABLE", "NOT_APPLICABLE", "REQUIRES_INFORMATION",
        "REQUIRES_REVIEW", "BLOCKED_DRAFT_NOT_PRODUCTION",
    }


def test_rule_output_mapping_is_exposed_and_matches_authored_data(engine, dataset):
    d = engine.evaluate_requirement("P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, NP)
    # YAML parses bare TRUE/FALSE as booleans; rules.py normalizes those to
    # "TRUE"/"FALSE" string keys for lookup. Mirror that same normalization
    # here rather than comparing against the raw YAML dict directly.
    raw = dataset.rule_versions["RULE-0001-V2"]["output_mapping"]
    normalized = {}
    for k, v in raw.items():
        if k is True:
            normalized["TRUE"] = v
        elif k is False:
            normalized["FALSE"] = v
        else:
            normalized[str(k)] = v
    assert d["explanation"]["rule_output_mapping"] == normalized


def test_declared_required_facts_come_from_dataset_not_invented(engine, dataset):
    d = engine.evaluate_requirement("P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, NP)
    authored = dataset.rule_versions["RULE-0001-V2"]["required_project_facts"]
    assert d["explanation"]["declared_required_facts"] == authored


def test_input_facts_used_reflects_only_facts_actually_consulted(engine):
    facts = dict({"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, **{"project.some_unrelated_fact_not_consulted": "ignored"})
    d = engine.evaluate_requirement("P", "REQ-0001", facts, NP)
    assert d["explanation"]["input_facts_used"] == ["project.holds_prior_environmental_clearance", "project.is_white_category_industrial_plant", "project.likely_to_discharge_sewage_or_trade_effluent"]


def test_explanation_json_serializable_for_every_requirement(engine, dataset):
    import json
    for req_id in dataset.requirements:
        d = engine.evaluate_requirement("P", req_id, {}, NP)
        encoded = json.dumps(d["explanation"])
        assert json.loads(encoded)["requirement_id"] == req_id


def test_explanation_present_for_missing_requirement_too(engine):
    d = engine.evaluate_requirement("P", "REQ-DOES-NOT-EXIST", {}, NP)
    assert d["final_state"] == "BLOCKED_UNKNOWN_REQUIREMENT"
    assert d["explanation"]["final_state"] == "BLOCKED_UNKNOWN_REQUIREMENT"
    assert d["explanation"]["narrative"]
