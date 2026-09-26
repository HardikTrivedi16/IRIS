"""
Phase 9 Section 8 — Decision Snapshot tests: input facts captured, rule
version captured, engine version captured, evaluation mode captured, and
the snapshot is reproducible from what was actually used (not merely a
reference to current project state).
"""
from iris_engine.rules import EvaluationMode
from iris_engine.snapshot import build_snapshot, compute_decision_id, DecisionStore

NP = EvaluationMode.NON_PRODUCTION

REQUIRED_SNAPSHOT_FIELDS = {
    "decision_id", "project_id", "evaluated_at", "engine_version",
    "rule_version_ids", "input_fact_snapshot", "evaluation_mode",
    "result", "explanation",
}


def test_snapshot_has_all_required_fields(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P1", "REQ-0001", facts, NP, evaluated_at="fixed")
    snap = build_snapshot(decision=d, project_facts=facts)
    assert REQUIRED_SNAPSHOT_FIELDS.issubset(snap.keys())
    assert snap["project_id"] == "P1"
    assert snap["evaluated_at"] == "fixed"
    assert snap["result"] == d["final_state"]


def test_snapshot_captures_input_facts_actually_used_not_the_whole_project(engine):
    facts = dict({"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, **{"project.totally_unrelated": "should not appear"})
    d = engine.evaluate_requirement("P1", "REQ-0001", facts, NP)
    snap = build_snapshot(decision=d, project_facts=facts)
    assert snap["input_fact_snapshot"] == {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}


def test_snapshot_captures_rule_version_ids_including_classification_group(engine):
    facts = {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 60000,
             "project.dairy_milk_solids_capacity": 1000}
    d = engine.evaluate_requirement("P1", "REQ-0004", facts, NP)
    snap = build_snapshot(decision=d, project_facts=facts)
    assert set(snap["rule_version_ids"]) == {"RULE-0004-V1", "RULE-0005-V1", "RULE-0006-V1"}


def test_snapshot_captures_engine_version_and_mode(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P1", "REQ-0001", facts, NP)
    snap = build_snapshot(decision=d, project_facts=facts)
    assert snap["engine_version"] == d["engine_version"]
    assert snap["evaluation_mode"] == "NON_PRODUCTION"


def test_snapshot_values_reflect_what_was_actually_used_at_call_time(engine):
    # Build a snapshot, then mutate the facts dict the caller holds -- the
    # snapshot must not change, because it captured the values, not a
    # reference to the live dict.
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P1", "REQ-0001", facts, NP)
    snap = build_snapshot(decision=d, project_facts=facts)
    facts["project.likely_to_discharge_sewage_or_trade_effluent"] = False
    assert snap["input_fact_snapshot"]["project.likely_to_discharge_sewage_or_trade_effluent"] is True


def test_compute_decision_id_is_deterministic_and_order_independent():
    kwargs = dict(
        project_id="P", requirement_id="REQ-0001", engine_version="v1",
        input_fact_snapshot={"a": 1, "b": 2}, evaluation_mode="NON_PRODUCTION",
    )
    id1 = compute_decision_id(rule_versions=[("RV-1", "DRAFT"), ("RV-2", "ACTIVE")], **kwargs)
    id2 = compute_decision_id(rule_versions=[("RV-2", "ACTIVE"), ("RV-1", "DRAFT")], **kwargs)
    assert id1 == id2


def test_compute_decision_id_changes_when_status_changes():
    kwargs = dict(
        project_id="P", requirement_id="REQ-0001", engine_version="v1",
        input_fact_snapshot={"a": 1}, evaluation_mode="NON_PRODUCTION",
    )
    id_draft = compute_decision_id(rule_versions=[("RV-1", "DRAFT")], **kwargs)
    id_active = compute_decision_id(rule_versions=[("RV-1", "ACTIVE")], **kwargs)
    assert id_draft != id_active


def test_decision_store_put_and_get_roundtrip(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P1", "REQ-0001", facts, NP)
    snap = build_snapshot(decision=d, project_facts=facts)
    store = DecisionStore()
    store.put(snap)
    assert len(store) == 1
    assert snap["decision_id"] in store
    fetched = store.get(snap["decision_id"])
    assert fetched == snap


def test_decision_store_get_missing_id_returns_none():
    store = DecisionStore()
    assert store.get("DEC-does-not-exist") is None
