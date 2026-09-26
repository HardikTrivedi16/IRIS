"""
Phase 9 Section 11 — a stored Decision must NOT silently change because a
newer Rule Version exists, current project facts changed, current
regulatory data changed, or the engine was upgraded.
"""
import copy

import pytest

from iris_engine.rules import EvaluationMode
from iris_engine.snapshot import build_snapshot, DecisionStore, SnapshotConflictError

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION


def test_stored_snapshot_survives_rule_version_status_change(engine, dataset):
    # REQ-0003 became ACTIVE in Verification Batch 1, so use REQ-0001 (RULE-0001-V2, still DRAFT).
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True,
             "project.is_white_category_industrial_plant": False,
             "project.holds_prior_environmental_clearance": False}
    d1 = engine.evaluate_requirement("P", "REQ-0001", facts, NP, evaluated_at="t1")
    snap1 = build_snapshot(decision=d1, project_facts=facts)
    store = DecisionStore()
    store.put(snap1)

    original_status = dataset.rule_versions["RULE-0001-V2"]["status"]
    dataset.rule_versions["RULE-0001-V2"]["status"] = "ACTIVE"
    try:
        # A fresh evaluation now sees the promoted rule and is no longer
        # blocked -- a genuinely different Decision.
        d2 = engine.evaluate_requirement("P", "REQ-0001", facts, PROD, evaluated_at="t2")
        assert d2["final_state"] != "BLOCKED_DRAFT_NOT_PRODUCTION"

        # But the historical snapshot recorded before the promotion is
        # completely unaffected.
        refetched = store.get(snap1["decision_id"])
        assert refetched == snap1
        assert refetched["explanation"]["rule_version_status"] == "DRAFT"
    finally:
        dataset.rule_versions["RULE-0001-V2"]["status"] = original_status


def test_stored_snapshot_survives_current_project_facts_changing(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}
    d1 = engine.evaluate_requirement("P", "REQ-0001", facts, NP, evaluated_at="t1")
    snap1 = build_snapshot(decision=d1, project_facts=facts)
    store = DecisionStore()
    store.put(snap1)

    # "Current" project facts change for a later evaluation of the same
    # project/requirement.
    new_facts = {"project.likely_to_discharge_sewage_or_trade_effluent": False}
    d2 = engine.evaluate_requirement("P", "REQ-0001", new_facts, NP, evaluated_at="t2")
    assert d2["final_state"] != d1["final_state"]

    refetched = store.get(snap1["decision_id"])
    assert refetched["result"] == "APPLICABLE"
    assert refetched["input_fact_snapshot"] == {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}


def test_decision_store_refuses_to_silently_overwrite_a_conflicting_snapshot(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P", "REQ-0001", facts, NP, evaluated_at="t1")
    snap = build_snapshot(decision=d, project_facts=facts)
    store = DecisionStore()
    store.put(snap)

    tampered = copy.deepcopy(snap)
    tampered["result"] = "SOMETHING_ELSE"
    with pytest.raises(SnapshotConflictError):
        store.put(tampered)

    # Original content must still be exactly what was first stored.
    assert store.get(snap["decision_id"]) == snap


def test_putting_the_identical_snapshot_twice_is_a_harmless_no_op(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P", "REQ-0001", facts, NP, evaluated_at="t1")
    snap = build_snapshot(decision=d, project_facts=facts)
    store = DecisionStore()
    store.put(snap)
    store.put(copy.deepcopy(snap))  # identical content, same id -> fine
    assert len(store) == 1
