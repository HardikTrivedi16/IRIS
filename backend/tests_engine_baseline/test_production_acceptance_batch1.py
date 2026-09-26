"""
Verification Batch 1 - PRODUCTION acceptance tests.

The 12 human-approved Rule Versions are ACTIVE, so their Requirements return authoritative results in
PRODUCTION mode. Everything else stays fail-closed, SUPERSEDED versions can never be authoritative, and the
diagnostic mode is unchanged. Approval covers the ENCODED scope only (limitations remain in the Rule Versions).
"""
import pytest

from iris_engine.rules import (
    EvaluationMode, evaluate_rule_version, BLOCKED_DRAFT_NOT_PRODUCTION, BLOCKED_UNKNOWN_STATUS,
)
from iris_engine.validate import validate_dataset

PROD = EvaluationMode.PRODUCTION
NP = EvaluationMode.NON_PRODUCTION

APPROVED = {
    "REQ-0003": "RULE-0003-V1", "REQ-0006": "RULE-0009-V1", "REQ-0007": "RULE-0010-V1",
    "REQ-0009": "RULE-0012-V2", "REQ-0010": "RULE-0013-V2", "REQ-0015": "RULE-0023-V1",
    "REQ-0017": "RULE-0025-V2", "REQ-0018": "RULE-0026-V2", "REQ-0019": "RULE-0027-V2",
}
STILL_DRAFT = ["REQ-0001", "REQ-0002", "REQ-0004", "REQ-0005", "REQ-0008", "REQ-0011", "REQ-0012",
               "REQ-0013", "REQ-0014", "REQ-0016", "REQ-0020", "REQ-0021"]

GATE = {"project.manufactures_drugs_for_sale_or_distribution": True, "project.pharma_activity_type": "FORMULATIONS"}
CLS = "project.drug_schedule_classification"


def prod(engine, req, facts):
    d = engine.evaluate_requirement("P", req, facts, PROD)
    assert d["is_non_production_result"] is False
    assert d["rule_version_status"] == "ACTIVE"
    assert d["final_state"] != BLOCKED_DRAFT_NOT_PRODUCTION
    return d


# --- REQ-0006 / REQ-0007 -----------------------------------------------------------------
def test_boiler_registration_boundary_authoritative(engine):
    at = {"project.boiler_volumetric_capacity_litres": 25, "project.boiler_design_gauge_pressure_kg_cm2": 1}
    assert prod(engine, "REQ-0006", at)["final_state"] == "APPLICABLE"
    below = {"project.boiler_volumetric_capacity_litres": 24.9, "project.boiler_design_gauge_pressure_kg_cm2": 1}
    assert prod(engine, "REQ-0006", below)["final_state"] == "NOT_APPLICABLE"
    assert prod(engine, "REQ-0006", {})["final_state"] == "REQUIRES_INFORMATION"


def test_boiler_certificate_authoritative(engine):
    assert prod(engine, "REQ-0007", {"project.holds_boiler_certificate": True})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0007", {"project.holds_boiler_certificate": False})["final_state"] == "NOT_APPLICABLE"


# --- REQ-0009 ------------------------------------------------------------------------------
def test_legal_metrology_new_fact_authoritative(engine):
    f = "project.prepacks_or_imports_commodities_for_sale_distribution_or_delivery"
    assert prod(engine, "REQ-0009", {f: True})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0009", {f: False})["final_state"] == "NOT_APPLICABLE"
    # the superseded retail-only fact alone gives no authoritative answer
    assert prod(engine, "REQ-0009", {"project.prepacks_commodities_for_retail_sale": True})["final_state"] == "REQUIRES_INFORMATION"


# --- REQ-0010 ------------------------------------------------------------------------------
def test_hazardous_waste_normal_and_exempt_authoritative(engine):
    W = "project.generates_or_handles_scheduled_hazardous_waste"
    CNR = "project.state_board_consent_not_required_under_water_and_air_acts"
    H = "project.hands_over_hazardous_waste_to_authorised_actual_user_collector_or_disposal_facility"
    assert prod(engine, "REQ-0010", {W: True, CNR: False, H: True})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0010", {W: True, CNR: True, H: True})["final_state"] == "NOT_APPLICABLE"
    assert prod(engine, "REQ-0010", {W: True, CNR: True})["final_state"] == "REQUIRES_INFORMATION"
    assert prod(engine, "REQ-0010", {W: False})["final_state"] == "NOT_APPLICABLE"


# --- REQ-0003 classification family --------------------------------------------------------
@pytest.mark.parametrize("cls,rule", [
    ("NONE", "RULE-0017"), ("SCHEDULE_C_OR_C1", "RULE-0018"),
    ("SCHEDULE_X_ONLY", "RULE-0019"), ("SCHEDULE_C_OR_C1_AND_X", "RULE-0019"),
])
def test_drug_classification_family_is_coherent_in_production(engine, cls, rule):
    d = prod(engine, "REQ-0003", dict(GATE, **{CLS: cls}))
    assert d["final_state"] == "APPLICABLE"
    block = d["classification"]
    assert block["combined_state"] == "APPLICABLE" and block["review_reason"] is None
    results = block["rule_results"]
    assert results[rule] == "APPLICABLE"
    assert [r for r, s in results.items() if s == "APPLICABLE"] == [rule]  # exactly one pathway, no overlap review
    assert set(results) == {"RULE-0017", "RULE-0018", "RULE-0019"}
    assert "BLOCKED_DRAFT_NOT_PRODUCTION" not in results.values()  # no DRAFT member left in the family


def test_drug_gate_and_missing_classification_in_production(engine):
    assert prod(engine, "REQ-0003", dict(GATE, **{"project.pharma_activity_type": "REPACKING"}))["final_state"] == "NOT_APPLICABLE"
    assert prod(engine, "REQ-0003", GATE)["final_state"] == "REQUIRES_INFORMATION"


def test_drug_retention_authoritative(engine):
    f = "project.holds_drug_manufacturing_licence"
    assert prod(engine, "REQ-0015", {f: True})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0015", {f: False})["final_state"] == "NOT_APPLICABLE"


# --- REQ-0017 / 0018 / 0019 ------------------------------------------------------------------
def test_battery_producer_authoritative(engine):
    assert prod(engine, "REQ-0017", {"project.places_batteries_on_market": True})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0017", {"project.places_batteries_on_market": False})["final_state"] == "NOT_APPLICABLE"


def test_ewaste_producer_and_manufacturer_authoritative(engine):
    OWN = "project.sells_schedule1_eee_under_own_brand"
    IMP = "project.sells_imported_schedule1_eee_or_imports_used_schedule1_eee"
    MS = "project.msme_classification"
    assert prod(engine, "REQ-0018", {OWN: True, MS: "SMALL"})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0018", {OWN: False, IMP: True, MS: "MEDIUM"})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0018", {OWN: True, MS: "MICRO"})["final_state"] == "NOT_APPLICABLE"
    M = "project.manufactures_schedule1_eee"
    assert prod(engine, "REQ-0019", {M: True, MS: "NOT_MSME"})["final_state"] == "APPLICABLE"
    assert prod(engine, "REQ-0019", {M: True, MS: "MICRO"})["final_state"] == "NOT_APPLICABLE"


# --- lifecycle gate remains intact ----------------------------------------------------------------
def test_every_approved_requirement_is_active_and_has_an_approved_ver(dataset):
    approved_targets = {v["target_id"] for v in dataset.verifications.values() if v["result"] == "APPROVED"}
    assert set(APPROVED.values()) <= approved_targets
    assert len(dataset.verifications) == 12
    for v in dataset.verifications.values():
        assert v["reviewer"] == "Hardik Trivedi" and v["result"] == "APPROVED" and v["target_type"] == "RULE_VERSION"
    active = {k for k, rv in dataset.rule_versions.items() if rv["status"] == "ACTIVE"}
    assert active == set(APPROVED.values()) | {"RULE-0003-V1", "RULE-0017-V1", "RULE-0018-V1", "RULE-0019-V1"} - set()


@pytest.mark.parametrize("req", STILL_DRAFT)
def test_unrelated_requirements_stay_blocked_in_production(engine, req):
    assert engine.evaluate_requirement("P", req, {}, PROD)["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


@pytest.mark.parametrize("rvid", ["RULE-0012-V1", "RULE-0013-V1", "RULE-0025-V1", "RULE-0026-V1", "RULE-0027-V1",
                                  "RULE-0014-V1", "RULE-0015-V1"])
def test_superseded_versions_are_never_authoritative(dataset, rvid):
    assert dataset.rule_versions[rvid]["status"] == "SUPERSEDED"
    for mode in (PROD, NP):
        r = evaluate_rule_version(rvid, dataset, {}, mode)
        assert r.blocked is True and r.final_state == BLOCKED_UNKNOWN_STATUS


def test_diagnostic_mode_unchanged(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION" and d["is_non_production_result"] is True
    # an ACTIVE version evaluated diagnostically yields the same state as in Production
    facts = {"project.holds_boiler_certificate": True}
    assert engine.evaluate_requirement("P", "REQ-0007", facts, NP)["final_state"] == \
        engine.evaluate_requirement("P", "REQ-0007", facts, PROD)["final_state"]


def test_status_gate_still_blocks_when_an_approved_version_is_not_active(engine, dataset):
    original = dataset.rule_versions["RULE-0010-V1"]["status"]
    dataset.rule_versions["RULE-0010-V1"]["status"] = "DRAFT"
    try:
        d = engine.evaluate_requirement("P", "REQ-0007", {"project.holds_boiler_certificate": True}, PROD)
        assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    finally:
        dataset.rule_versions["RULE-0010-V1"]["status"] = original


def test_active_promotion_gate_fails_without_an_approved_ver(dataset):
    from iris_engine.loader import RegulatoryDataset  # noqa: F401
    import os
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")
    ver_id, ver = next((k, v) for k, v in dataset.verifications.items() if v["target_id"] == "RULE-0009-V1")
    del dataset.verifications[ver_id]
    try:
        report = validate_dataset(root, dataset)
        assert not report.passed
        assert any("RULE-0009-V1" in x and "APPROVED" in x for x in report.active_promotion_violations)
    finally:
        dataset.verifications[ver_id] = ver
    assert validate_dataset(root, dataset).passed
