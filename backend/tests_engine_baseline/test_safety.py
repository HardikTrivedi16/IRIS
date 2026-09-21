from iris_engine.rules import EvaluationMode, BLOCKED_DRAFT_NOT_PRODUCTION

PROD = EvaluationMode.PRODUCTION
NP = EvaluationMode.NON_PRODUCTION


def test_draft_rule_cannot_be_production_decision(engine, dataset):
    # all 6 rule versions are currently DRAFT
    for rv_id, rv in dataset.rule_versions.items():
        assert rv.get("status") == "DRAFT"

    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, PROD)
    assert d["final_state"] == BLOCKED_DRAFT_NOT_PRODUCTION
    assert d["final_state"] not in ("APPLICABLE", "NOT_APPLICABLE", "REQUIRES_INFORMATION", "REQUIRES_REVIEW")


def test_draft_rule_labelled_non_production_when_evaluated(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    assert d["is_non_production_result"] is True
    assert d["evaluation_mode"] == "NON_PRODUCTION"
    assert d["final_state"] == "APPLICABLE"


def test_zero_executable_dependencies(dataset):
    assert dataset.dependencies_index.get("dependencies", []) == []
    assert dataset.dependencies_index.get("counts", {}).get("total_dependencies") == 0
    # five review candidates exist but must not be executed
    items = dataset.dependency_review_register.get("review_items", [])
    assert len(items) == 5
    for item in items:
        assert item.get("current_status") in ("REQUIRES_REVIEW", "UNKNOWN")


def test_dependency_result_reports_zero_edges(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    dep = d["dependency_result"]
    assert dep["verified_edges_as_target"] == []
    assert dep["verified_edges_as_source"] == []


def test_unresolved_overlap_remains_review_never_resolved(engine):
    d = engine.evaluate_requirement("P", "REQ-0004",
        {"project.industry": "FOOD", "project.dairy_liquid_milk_capacity": 60000,
         "project.dairy_milk_solids_capacity": 1000}, NP)
    assert d["final_state"] == "REQUIRES_REVIEW"
    assert d["conflict_id"] == "OVERLAP-0001"


def test_provenance_chain_intact(engine, dataset):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, EvaluationMode.NON_PRODUCTION)
    prov = d["provenance"]
    assert prov["requirement_id"] == "REQ-0001"
    assert prov["rule_id"] == "RULE-0001"
    assert prov["rule_version_id"] == "RULE-0001-V1"
    assert prov["regulatory_fact_ids"] == ["RF-0001"]
    assert prov["evidence_ids"] == ["EVID-MPCB-01"]
    assert prov["authority_id"] == "AUTH-MoEFCC"
    assert prov["instrument_id"] == "INST-WATER-74"
    assert "unresolved_note" in prov  # Phase 3/4 records not in this package — never fabricated


def test_unknown_status_fails_safe(dataset, engine):
    # simulate an unrecognized status via a synthetic in-memory rule version
    from iris_engine.rules import evaluate_rule_version
    ds = dataset
    fake_id = "RULE-TEST-BAD-STATUS-V1"
    ds.rule_versions[fake_id] = {
        "rule_version_id": fake_id,
        "rule_id": "RULE-TEST",
        "status": "PENDING_REVIEW_XYZ",  # not in the known enumeration
        "condition_expression_root_id": None,
        "output_mapping": {},
    }
    try:
        result = evaluate_rule_version(fake_id, ds, {}, EvaluationMode.PRODUCTION)
        assert result.blocked is True
        assert "BLOCKED" in result.final_state
    finally:
        del ds.rule_versions[fake_id]


def test_engine_version_and_timestamp_present(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, EvaluationMode.NON_PRODUCTION)
    assert d["engine_version"]
    assert d["evaluated_at"]
