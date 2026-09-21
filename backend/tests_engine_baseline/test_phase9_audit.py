"""
Phase 9 Section 14-15 — structured audit trail: covers what/when/engine/
rule-version/facts/conditions/decision/why/evidence/review-or-conflict, is
machine-readable, deterministic, and never leaks filesystem paths, stack
traces, or secret-shaped keys.
"""
import json

from iris_engine.rules import EvaluationMode
from iris_engine.audit import build_audit_record

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

REQUIRED_AUDIT_FIELDS = {
    "decision_id", "what_was_evaluated", "when", "engine_version",
    "rule_version_used", "facts_used", "conditions_returned",
    "decision_produced", "why", "evidence_and_provenance",
    "review_or_conflict", "evaluation_mode",
}


def test_audit_record_has_all_required_fields(engine):
    facts = {"project.drug_schedule_classification": "SCHEDULE_C"}
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    record = build_audit_record(d)
    assert REQUIRED_AUDIT_FIELDS.issubset(record.keys())
    assert record["decision_produced"] == "REQUIRES_REVIEW"
    assert record["why"]


def test_audit_record_is_json_serializable(engine):
    facts = {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 60000,
             "project.dairy_milk_solids_capacity": 1000}
    d = engine.evaluate_requirement("P", "REQ-0004", facts, NP)
    record = build_audit_record(d)
    encoded = json.dumps(record)
    decoded = json.loads(encoded)
    assert decoded["review_or_conflict"]["conflict_id"] == "OVERLAP-0001"


def test_audit_record_is_deterministic(engine):
    facts = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    d = engine.evaluate_requirement("P", "REQ-0001", facts, NP, evaluated_at="fixed")
    r1 = build_audit_record(d)
    r2 = build_audit_record(d)
    assert r1 == r2


def test_audit_record_never_leaks_source_file_paths_or_secret_shaped_keys(engine):
    facts = {"project.drug_schedule_classification": "SCHEDULE_C"}
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    record = build_audit_record(d)
    blob = json.dumps(record)
    for forbidden in ("_source_file", "/home/", "/mnt/", "secret", "credential", "password"):
        assert forbidden not in blob.lower() if forbidden.islower() else forbidden not in blob


def test_audit_record_for_blocked_draft_explains_the_block(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {}, PROD)
    assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    record = build_audit_record(d)
    assert record["decision_produced"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    assert record["rule_version_used"]["status"] == "DRAFT"
    assert record["why"]


def test_audit_record_handles_malformed_or_empty_decision_without_raising():
    assert build_audit_record({}) is not None
    assert build_audit_record({"final_state": "X"})["decision_produced"] == "X"
