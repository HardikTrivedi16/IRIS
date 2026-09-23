"""
Phase 8 §13 — Decision artifact testing. Every Decision must contain the
required fields where applicable, serialize cleanly to JSON, and be
deterministic/reproducible (ignoring timestamps) across repeated
evaluations of the same inputs.
"""
import json

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

REQUIRED_FIELDS = {
    "project_id", "requirement_id", "rule_id", "rule_version_id",
    "final_state", "review_reason", "conflict_id", "evaluated_at",
    "engine_version", "evaluation_mode", "is_non_production_result",
    "conditions_evaluated", "missing_project_fact_keys", "classification",
    "dependency_result", "provenance", "reason_text",
}


def test_decision_contains_all_required_fields(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    assert REQUIRED_FIELDS.issubset(d.keys())


def test_decision_contains_all_required_fields_for_classification_requirement(engine):
    d = engine.evaluate_requirement("P", "REQ-0004",
        {"project.industry": "FOOD", "project.food_subsector": "DAIRY", "project.dairy_liquid_milk_capacity": 60000,
         "project.dairy_milk_solids_capacity": 1000}, NP)
    assert REQUIRED_FIELDS.issubset(d.keys())
    assert d["classification"] is not None
    assert d["classification"]["conflict_id"] == "OVERLAP-0001"


def test_decision_json_serializable_for_every_requirement(engine):
    for req_id, facts in [
        ("REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True}),
        ("REQ-0002", {"project.plant_located_in_air_pollution_control_area": False}),
        ("REQ-0003", {"project.drug_schedule_classification": "SCHEDULE_C"}),
        ("REQ-0004", {"project.industry": "FOOD"}),
    ]:
        d = engine.evaluate_requirement("P", req_id, facts, NP)
        encoded = json.dumps(d)
        decoded = json.loads(encoded)
        assert decoded["requirement_id"] == req_id


def test_decision_json_serializable_when_blocked_draft(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, PROD)
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    assert decoded["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


def test_decision_deterministic_ignoring_timestamp(engine):
    facts = {"project.industry": "FOOD", "project.food_subsector": "DAIRY", "project.dairy_liquid_milk_capacity": 60000,
             "project.dairy_milk_solids_capacity": 1000}
    d1 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="2026-01-01T00:00:00Z")
    d2 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="2026-01-01T00:00:00Z")
    assert d1 == d2

    d3 = engine.evaluate_requirement("P", "REQ-0004", facts, NP, evaluated_at="2099-12-31T23:59:59Z")
    d1_copy = dict(d1)
    d3_copy = dict(d3)
    del d1_copy["evaluated_at"]
    del d3_copy["evaluated_at"]
    assert d1_copy == d3_copy  # everything except the timestamp is identical


def test_decision_repeated_evaluation_stable(engine):
    facts = {"project.drug_schedule_classification": "SCHEDULE_C"}
    results = [engine.evaluate_requirement("P", "REQ-0003", facts, NP,
                                            evaluated_at="fixed") for _ in range(10)]
    assert all(r == results[0] for r in results)


def test_conditions_evaluated_is_a_flat_list_of_dicts(engine):
    d = engine.evaluate_requirement("P", "REQ-0004",
        {"project.industry": "FOOD", "project.food_subsector": "DAIRY", "project.dairy_liquid_milk_capacity": 60000,
         "project.dairy_milk_solids_capacity": 1000}, NP)
    for c in d["conditions_evaluated"]:
        assert set(c.keys()) == {"condition_id", "result", "input_project_fact_keys",
                                  "missing_project_fact_keys", "error"}
        assert c["result"] in ("TRUE", "FALSE", "UNKNOWN", None)


def test_missing_project_fact_keys_is_deduplicated_and_sorted(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", {}, NP)
    keys = d["missing_project_fact_keys"]
    assert keys == sorted(set(keys))


def test_evaluate_all_requirements_returns_one_decision_per_requirement(engine, dataset):
    decisions = engine.evaluate_all_requirements("P", {}, NP, evaluated_at="fixed")
    assert len(decisions) == len(dataset.requirements)
    req_ids = {d["requirement_id"] for d in decisions}
    assert req_ids == set(dataset.requirements.keys())
