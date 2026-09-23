"""
Covers the seven test cases the integration brief calls out explicitly:

  1. production + draft rule -> never silently treated as production-active
  2. missing facts -> REQUIRES_INFORMATION, not a guess
  3. deterministic evaluation using real SIH data (RULE-0001 / REQ-0001)
  4. explainability -> explanation block present and populated
  5. decision persistence -> can be stored and retrieved by decision_id
  6. snapshot/audit -> not lost when a decision is persisted
  7. conflict/overlap -> OVERLAP-0001 (RULE-0005/RULE-0006), not invented
"""


def test_case1_draft_rule_never_silently_becomes_production_active(client):
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "PRODUCTION",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
            "persist": False,
        },
    )
    assert r.status_code == 200
    decision = r.json()["decision"]
    assert decision["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    assert decision["rule_version_status"] == "DRAFT"
    # The same inputs in NON_PRODUCTION mode DO get a real diagnostic result.
    r2 = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
            "persist": False,
        },
    )
    decision2 = r2.json()["decision"]
    assert decision2["final_state"] == "APPLICABLE"
    assert decision2["is_non_production_result"] is True


def test_case2_missing_facts_return_requires_information(client):
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0003",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {},
            "persist": False,
        },
    )
    decision = r.json()["decision"]
    assert decision["final_state"] == "REQUIRES_INFORMATION"
    assert "project.drug_schedule_classification" in decision["missing_project_fact_keys"]


def test_case3_deterministic_evaluation_matches_rule0001(client):
    payload = {
        "project_id": "freshbite",
        "requirement_id": "REQ-0001",
        "evaluation_mode": "NON_PRODUCTION",
        "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": False},
        "persist": False,
    }
    r1 = client.post("/api/v1/evaluate", json=payload)
    r2 = client.post("/api/v1/evaluate", json=payload)
    d1, d2 = r1.json()["decision"], r2.json()["decision"]
    assert d1["final_state"] == "NOT_APPLICABLE" == d2["final_state"]
    assert d1["rule_id"] == "RULE-0001"
    # Same inputs -> same decision_id (ignoring nothing but evaluated_at).
    assert d1["decision_id"] == d2["decision_id"]


def test_case4_explanation_block_present_and_populated(client):
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0002",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {"project.plant_located_in_air_pollution_control_area": True},
            "persist": False,
        },
    )
    explanation = r.json()["decision"]["explanation"]
    assert explanation["requirement_id"] == "REQ-0002"
    assert explanation["final_state"] == "APPLICABLE"
    assert explanation["narrative"]
    assert explanation["condition_evaluation_tree"] is not None
    assert explanation["rule_output_mapping"]
    assert explanation["engine_version"].startswith("iris-engine-")


def test_case5_and_6_decision_can_be_persisted_and_retrieved_with_snapshot_and_audit(client):
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0002",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {"project.plant_located_in_air_pollution_control_area": True},
            "persist": True,
        },
    )
    body = r.json()
    assert body["persistence"]["stored"] is True
    decision_id = body["decision"]["decision_id"]

    g = client.get(f"/api/v1/decisions/{decision_id}")
    assert g.status_code == 200
    record = g.json()
    assert record["decision"]["decision_id"] == decision_id
    assert record["snapshot"] is not None
    assert record["snapshot"]["result"] == "APPLICABLE"
    assert record["audit"] is not None
    assert record["audit"]["decision_produced"] == "APPLICABLE"
    # A stored decision must never silently change underneath a caller.
    g2 = client.get(f"/api/v1/decisions/{decision_id}")
    assert g2.json() == record


def test_persisting_the_same_decision_twice_is_idempotent_not_duplicated(client):
    payload = {
        "project_id": "mahapharm",
        "requirement_id": "REQ-0002",
        "evaluation_mode": "NON_PRODUCTION",
        "facts": {"project.plant_located_in_air_pollution_control_area": True},
        "persist": True,
    }
    r1 = client.post("/api/v1/evaluate", json=payload)
    r2 = client.post("/api/v1/evaluate", json=payload)
    assert r1.json()["decision"]["decision_id"] == r2.json()["decision"]["decision_id"]
    assert r1.json()["persistence"]["stored"] is True
    assert r2.json()["persistence"]["stored"] is True

    listing = client.get("/api/v1/projects/mahapharm/decisions", params={"requirement_id": "REQ-0002"})
    matching = [d for d in listing.json() if d["decision_id"] == r1.json()["decision"]["decision_id"]]
    assert len(matching) == 1  # not duplicated


def test_case7_fssai_overlap_conflict_is_surfaced_not_invented(client):
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "freshbite",
            "requirement_id": "REQ-0004",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {
                "project.industry": "FOOD",
                "project.food_subsector": "DAIRY",
                "project.dairy_liquid_milk_capacity": 60000,
                "project.dairy_milk_solids_capacity": 1000,
            },
            "persist": False,
        },
    )
    decision = r.json()["decision"]
    assert decision["final_state"] == "REQUIRES_REVIEW"
    assert decision["conflict_id"] == "OVERLAP-0001"
    assert decision["classification"]["rule_results"] == {
        "RULE-0005": "APPLICABLE",
        "RULE-0006": "APPLICABLE",
    }


def test_evaluate_all_returns_one_decision_per_dataset_requirement(client):
    from app import engine_service

    r = client.post(
        "/api/v1/evaluate/all",
        json={"project_id": "mahapharm", "evaluation_mode": "NON_PRODUCTION", "persist": False},
    )
    assert r.status_code == 200
    decisions = r.json()["decisions"]
    # Compare against the live dataset's own requirement list rather than
    # a hardcoded count, so this test does not go stale the next time a
    # Requirement is added (as happened silently between the original
    # 4-Requirement Phase 5/6 package and the later Shared+Food/Pharma
    # tranches, only caught now that this file is run again).
    expected_ids = sorted(engine_service.get_dataset().requirements.keys())
    assert sorted(d["requirement_id"] for d in decisions) == expected_ids


def test_evaluate_unknown_requirement_fails_safe(client):
    r = client.post(
        "/api/v1/evaluate",
        json={"project_id": "mahapharm", "requirement_id": "REQ-9999", "persist": False},
    )
    assert r.status_code == 200
    decision = r.json()["decision"]
    assert decision["final_state"] == "BLOCKED_UNKNOWN_REQUIREMENT"


def test_evaluate_malformed_request_is_422(client):
    r = client.post("/api/v1/evaluate", json={"project_id": "mahapharm"})  # missing requirement_id
    assert r.status_code == 422


def test_unknown_decision_id_is_404(client):
    r = client.get("/api/v1/decisions/DEC-DOES-NOT-EXIST")
    assert r.status_code == 404
