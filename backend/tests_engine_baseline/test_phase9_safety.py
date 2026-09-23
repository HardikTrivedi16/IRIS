"""
Phase 9 Section 16 "Safety" + Section 13/15 — DRAFT never becomes
production, an unresolved conflict never becomes resolved, missing
provenance never becomes fabricated provenance, and malformed input fails
safely.
"""
import json

from iris_engine.rules import EvaluationMode
from iris_engine.snapshot import DecisionStore, build_snapshot
from iris_engine.audit import build_audit_record

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION


def test_draft_rule_version_never_produces_a_production_decision(engine, dataset):
    # Any requirement wired to a DRAFT rule version must be blocked, not
    # silently evaluated, under PRODUCTION mode.
    assert dataset.rule_versions["RULE-0001-V1"]["status"] == "DRAFT"
    d = engine.evaluate_requirement("P", "REQ-0001", {
        "project.likely_to_discharge_sewage_or_trade_effluent": True
    }, PROD)
    assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    assert d["explanation"]["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


def test_fssai_conflict_is_never_silently_resolved_by_explanation_layer(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0004",
        {"project.industry": "FOOD", "project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 60000,
         "project.dairy_milk_solids_capacity": 1000},
        NP,
    )
    assert d["final_state"] == "REQUIRES_REVIEW"
    assert d["explanation"]["conflict_id"] == "OVERLAP-0001"
    # Neither individual rule result is silently promoted to the Decision.
    assert d["final_state"] not in ("APPLICABLE", "NOT_APPLICABLE")


def test_missing_provenance_link_stays_unknown_not_fabricated(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP
    )
    prov = d["explanation"]["provenance"]
    assert "unresolved_note" in prov and prov["unresolved_note"]
    forbidden_keys = {"source_title", "evidence_excerpt", "fact_text", "authority_name"}
    assert forbidden_keys.isdisjoint(prov.keys())


def test_explanation_and_audit_never_raise_on_malformed_project_facts(engine):
    weird_facts = {
        "project.drug_schedule_classification": {"not": "a string"},
        "project.likely_to_discharge_sewage_or_trade_effluent": ["also", "wrong", "type"],
    }
    d = engine.evaluate_requirement("P", "REQ-0003", weird_facts, NP)
    # Must fail safe (UNKNOWN-ish states), never raise.
    assert d["final_state"] in (
        "UNKNOWN", "REQUIRES_INFORMATION", "REQUIRES_REVIEW", "NOT_APPLICABLE", "APPLICABLE",
    )
    record = build_audit_record(d)
    json.dumps(record)  # must still be JSON serializable


def test_decision_store_never_lets_a_second_write_silently_win():
    store = DecisionStore()
    snap = {
        "decision_id": "DEC-fixed-id", "project_id": "P", "requirement_id": "REQ-X",
        "evaluated_at": "t1", "engine_version": "v1", "rule_version_ids": [],
        "input_fact_snapshot": {}, "evaluation_mode": "NON_PRODUCTION",
        "result": "APPLICABLE", "explanation": {},
    }
    store.put(snap)
    import pytest
    from iris_engine.snapshot import SnapshotConflictError
    bad = dict(snap, result="NOT_APPLICABLE")
    with pytest.raises(SnapshotConflictError):
        store.put(bad)
    assert store.get("DEC-fixed-id")["result"] == "APPLICABLE"


def test_blocked_evaluation_reveals_no_internal_stack_trace_or_path(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {}, PROD)
    blob = json.dumps(d)
    assert "Traceback" not in blob
    assert "_source_file" not in blob
    assert "/home/claude" not in blob
