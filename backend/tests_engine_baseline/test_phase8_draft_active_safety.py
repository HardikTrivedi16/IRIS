"""
Phase 8 §8 — DRAFT/ACTIVE safety, extended beyond Phase 7's test_safety.py:
every one of the 6 current DRAFT rule versions individually blocked in
PRODUCTION mode; a synthetic ACTIVE rule version proceeding normally in
PRODUCTION; an unknown-status rule version failing safe; and a missing
rule version ID failing safe. The real dataset's actual statuses are never
changed -- synthetic rule versions are added under new IDs and removed in
a `finally` block.
"""
import copy

import pytest

from iris_engine.rules import (
    evaluate_rule_version, EvaluationMode,
    BLOCKED_DRAFT_NOT_PRODUCTION, BLOCKED_UNKNOWN_STATUS,
)

PROD = EvaluationMode.PRODUCTION
NP = EvaluationMode.NON_PRODUCTION

ALL_RULE_VERSION_IDS = [f"RULE-{i:04d}-V1" for i in range(1, 7)]


@pytest.mark.parametrize("rv_id", ALL_RULE_VERSION_IDS)
def test_every_current_draft_rule_blocked_in_production(dataset, rv_id):
    assert dataset.rule_versions[rv_id]["status"] == "DRAFT"
    r = evaluate_rule_version(rv_id, dataset, {}, PROD)
    assert r.blocked is True
    assert r.final_state == BLOCKED_DRAFT_NOT_PRODUCTION
    assert r.final_state not in ("APPLICABLE", "NOT_APPLICABLE", "REQUIRES_INFORMATION", "REQUIRES_REVIEW")
    assert r.is_non_production is False  # blocked, never presented as any kind of result


@pytest.mark.parametrize("rv_id", ALL_RULE_VERSION_IDS)
def test_every_current_draft_rule_evaluates_normally_non_production(dataset, rv_id):
    r = evaluate_rule_version(rv_id, dataset, {}, NP)
    assert r.blocked is False
    assert r.is_non_production is True
    assert r.final_state in ("REQUIRES_INFORMATION", "UNKNOWN")  # empty facts -> unresolved
    assert r.final_state != BLOCKED_DRAFT_NOT_PRODUCTION


def test_dataset_statuses_never_actually_changed_by_running_these_tests(dataset):
    for rv_id in ALL_RULE_VERSION_IDS:
        assert dataset.rule_versions[rv_id]["status"] == "DRAFT"


def test_synthetic_active_rule_version_proceeds_in_production(dataset):
    fake_cond_id = "TEST-COND-ACTIVE"
    fake_rv_id = "TEST-RULE-ACTIVE-V1"
    original_conditions = copy.deepcopy(dataset.conditions)
    try:
        dataset.conditions[fake_cond_id] = {
            "predicate_type": "BOOLEAN_EQUALS",
            "target_variable_key": "project.test_active_flag",
            "operator": "==", "comparison_value": True, "child_condition_ids": [],
        }
        dataset.rule_versions[fake_rv_id] = {
            "rule_version_id": fake_rv_id, "rule_id": "TEST-RULE-ACTIVE",
            "status": "ACTIVE",
            "condition_expression_root_id": fake_cond_id,
            "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        }
        r = evaluate_rule_version(fake_rv_id, dataset, {"project.test_active_flag": True}, PROD)
        assert r.blocked is False
        assert r.final_state == "APPLICABLE"
        assert r.is_non_production is False
    finally:
        del dataset.rule_versions[fake_rv_id]
        dataset.conditions = original_conditions


def test_synthetic_active_rule_version_also_labelled_non_production_if_run_that_way(dataset):
    # ACTIVE rules CAN be run in NON_PRODUCTION diagnostic mode too; the
    # is_non_production flag reflects the rule's own status, not the mode,
    # so an ACTIVE rule is never mislabelled non-production.
    fake_cond_id = "TEST-COND-ACTIVE-2"
    fake_rv_id = "TEST-RULE-ACTIVE-2-V1"
    original_conditions = copy.deepcopy(dataset.conditions)
    try:
        dataset.conditions[fake_cond_id] = {
            "predicate_type": "BOOLEAN_EQUALS",
            "target_variable_key": "project.test_active_flag_2",
            "operator": "==", "comparison_value": True, "child_condition_ids": [],
        }
        dataset.rule_versions[fake_rv_id] = {
            "rule_version_id": fake_rv_id, "rule_id": "TEST-RULE-ACTIVE-2",
            "status": "ACTIVE",
            "condition_expression_root_id": fake_cond_id,
            "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        }
        r = evaluate_rule_version(fake_rv_id, dataset, {"project.test_active_flag_2": True}, NP)
        assert r.is_non_production is False
    finally:
        del dataset.rule_versions[fake_rv_id]
        dataset.conditions = original_conditions


@pytest.mark.parametrize("bad_status", ["PENDING", "UNDER_REVIEW", "", "unknown_lowercase", None])
def test_unknown_or_unsupported_status_fails_safe(dataset, bad_status):
    fake_rv_id = "TEST-RULE-BADSTATUS-V1"
    dataset.rule_versions[fake_rv_id] = {
        "rule_version_id": fake_rv_id, "rule_id": "TEST-RULE-BADSTATUS",
        "status": bad_status,
        "condition_expression_root_id": None,
        "output_mapping": {},
    }
    try:
        r = evaluate_rule_version(fake_rv_id, dataset, {}, PROD)
        assert r.blocked is True
        assert r.final_state == BLOCKED_UNKNOWN_STATUS
        assert r.final_state not in ("APPLICABLE", "NOT_APPLICABLE", "REQUIRES_INFORMATION", "REQUIRES_REVIEW")
    finally:
        del dataset.rule_versions[fake_rv_id]


def test_missing_rule_version_id_fails_safe(dataset):
    r = evaluate_rule_version("RULE-DOES-NOT-EXIST-V1", dataset, {}, PROD)
    assert r.blocked is True
    assert r.final_state == BLOCKED_UNKNOWN_STATUS
    assert r.status == "UNKNOWN"


def test_missing_rule_version_via_full_engine_reports_blocked_no_rule(engine, dataset):
    # a Requirement whose evaluated_by_rule_id points at a real Rule but
    # that Rule's latest_rule_version_id is corrupted (synthetic-only)
    import copy as _copy
    original = _copy.deepcopy(dataset.rules_index)
    try:
        for r in dataset.rules_index["rules"]:
            if r["rule_id"] == "RULE-0001":
                r["latest_rule_version_id"] = "RULE-DOES-NOT-EXIST-V1"
        d = engine.evaluate_requirement("P", "REQ-0001", {}, EvaluationMode.PRODUCTION)
        assert d["final_state"] == BLOCKED_UNKNOWN_STATUS
    finally:
        dataset.rules_index = original


def test_requirement_with_no_evaluated_by_rule_id_and_no_classification_group(dataset):
    # decision.py's BLOCKED_NO_RULE path: evaluated_by_rule_id is None and
    # there is no classification_rule_ids group either.
    from iris_engine.decision import build_requirement_decision
    original = copy.deepcopy(dataset.requirements)
    try:
        dataset.requirements["TEST-REQ-NO-RULE"] = {"evaluated_by_rule_id": None}
        d = build_requirement_decision("P", "TEST-REQ-NO-RULE", dataset, {},
                                        EvaluationMode.NON_PRODUCTION, evaluated_at="fixed")
        assert d["final_state"] == "BLOCKED_NO_RULE"
        assert "no evaluated_by_rule_id" in d["reason_text"]
    finally:
        dataset.requirements = original
