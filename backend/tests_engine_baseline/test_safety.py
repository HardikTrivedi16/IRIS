from iris_engine.rules import EvaluationMode, BLOCKED_DRAFT_NOT_PRODUCTION

PROD = EvaluationMode.PRODUCTION
NP = EvaluationMode.NON_PRODUCTION


def test_draft_rule_cannot_be_production_decision(engine, dataset):
    # No rule version is ACTIVE (some are SUPERSEDED since the FSSAI
    # currentness-correction pass — see rule_review_register.yaml
    # RULE-REV-0006 — but none has ever been promoted).
    for rv_id, rv in dataset.rule_versions.items():
        assert rv.get("status") in ("DRAFT", "SUPERSEDED", "ACTIVE")
        if rv.get("status") == "ACTIVE":  # only with an APPROVED human VER (Verification Batch 1)
            assert any(v.get("target_id") == rv_id and v.get("result") == "APPROVED"
                       for v in dataset.verifications.values()), rv_id

    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, PROD)
    assert d["final_state"] == BLOCKED_DRAFT_NOT_PRODUCTION
    assert d["final_state"] not in ("APPLICABLE", "NOT_APPLICABLE", "REQUIRES_INFORMATION", "REQUIRES_REVIEW")


def test_draft_rule_labelled_non_production_when_evaluated(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, NP)
    assert d["is_non_production_result"] is True
    assert d["evaluation_mode"] == "NON_PRODUCTION"
    assert d["final_state"] == "APPLICABLE"


def test_only_two_verified_executable_dependencies(dataset):
    # Dependency Tranche 1: four authored edges, two human-verified prerequisites.
    from iris_engine.dependencies import dependency_trust
    edges = dataset.dependencies_index.get("dependencies", [])
    assert len(edges) == 4
    assert dataset.dependencies_index.get("counts", {}).get("total_dependencies") == 4
    assert sum(dependency_trust(e, dataset) == "VERIFIED" for e in edges) == 2
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
        {"project.industry": "FOOD", "project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 60000,
         "project.dairy_milk_solids_capacity": 1000}, NP)
    assert d["final_state"] == "REQUIRES_REVIEW"
    assert d["conflict_id"] == "OVERLAP-0001"


def test_provenance_chain_intact(engine, dataset):
    d = engine.evaluate_requirement("P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}, EvaluationMode.NON_PRODUCTION)
    prov = d["provenance"]
    assert prov["requirement_id"] == "REQ-0001"
    assert prov["rule_id"] == "RULE-0001"
    assert prov["rule_version_id"] == "RULE-0001-V2"
    assert prov["regulatory_fact_ids"] == ["RF-0001", "RF-0034"]
    assert prov["evidence_ids"] == ["EVID-MPCB-01", "EVID-MPCB-03", "EVID-MPCB-04", "EVID-MPCB-07"]
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
