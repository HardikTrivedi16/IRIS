"""
Verification Batch 2 - PRODUCTION acceptance tests.

RULE-0002-V2, RULE-0007-V1, RULE-0014-V3, RULE-0015-V3 and RULE-0016-V2 are human-approved (VER-0013..VER-0017)
and ACTIVE, so REQ-0002/0005/0011/0012/0013 return authoritative results in PRODUCTION mode. Approval covers the
ENCODED scope only (limitations stay in the Rule Versions). REQ-0001 (Water) and REQ-0004 stay fail-closed.
"""
import pytest

from iris_engine.rules import EvaluationMode, evaluate_rule_version
from iris_engine.validate import validate_dataset

PROD = EvaluationMode.PRODUCTION
NP = EvaluationMode.NON_PRODUCTION
CR = 10_000_000
IND, SUB, TO = "project.industry", "project.food_subsector", "project.annual_turnover_inr"
WC, PWR = "project.worker_count", "project.manufacturing_process_uses_power"
APCA = "project.plant_located_in_air_pollution_control_area"
WHITE = "project.is_white_category_industrial_plant"
PEC = "project.holds_prior_environmental_clearance"

BATCH1_ACTIVE = {"RULE-0003-V1", "RULE-0009-V1", "RULE-0010-V1", "RULE-0012-V2", "RULE-0013-V2", "RULE-0017-V1",
                 "RULE-0018-V1", "RULE-0019-V1", "RULE-0023-V1", "RULE-0025-V2", "RULE-0026-V2", "RULE-0027-V2"}
BATCH2_ACTIVE = {"RULE-0002-V2", "RULE-0007-V1", "RULE-0014-V3", "RULE-0015-V3", "RULE-0016-V2"}

SAME_BANDS = ["OTHER_FOOD_PROCESSING", "DAIRY", "VEGETABLE_OIL", "SLAUGHTER", "MEAT_PROCESSING", "FISH_PRODUCTS",
              "SUBSTANCES_ADDED_TO_FOOD"]
ALWAYS_CENTRAL = ["HEALTH_SUPPLEMENT_NUTRACEUTICAL", "AYURVEDA_AAHARA", "PROPRIETARY_FOOD", "NON_SPECIFIED_FOOD",
                  "RADIATION_PROCESSING", "EXPORT_ORIENTED_OR_EXPORTER_MANUFACTURER"]
NON_FOOD = ["PHARMACEUTICAL", "AUTOMOBILE_EV", "ELECTRONICS_ESDM", "CHEMICALS"]


def prod(engine, req, facts):
    d = engine.evaluate_requirement("P", req, facts, PROD)
    assert d["is_non_production_result"] is False
    assert d["rule_version_status"] == "ACTIVE"
    assert not d["final_state"].startswith("BLOCKED")
    return d["final_state"]


def tiers(engine, facts):
    return tuple(prod(engine, r, facts) for r in ("REQ-0011", "REQ-0012", "REQ-0013"))  # Central, State, Registration


# --- REQ-0002 -----------------------------------------------------------------------------------
def test_air_normal_trigger_authoritative(engine):
    assert prod(engine, "REQ-0002", {APCA: True, WHITE: False}) == "APPLICABLE"
    assert prod(engine, "REQ-0002", {APCA: False, WHITE: False}) == "NOT_APPLICABLE"


def test_air_white_category_authoritative_not_applicable(engine):
    assert prod(engine, "REQ-0002", {APCA: True, WHITE: True}) == "NOT_APPLICABLE"


def test_air_prior_ec_remains_applicable_for_consent_to_operate(engine):
    assert prod(engine, "REQ-0002", {APCA: True, WHITE: False, PEC: True}) == "APPLICABLE"


def test_air_unknown_white_status_requires_information(engine):
    assert prod(engine, "REQ-0002", {APCA: True}) == "REQUIRES_INFORMATION"


# --- REQ-0005 -----------------------------------------------------------------------------------
@pytest.mark.parametrize("workers, power, expected", [
    (20, True, "APPLICABLE"), (19, True, "NOT_APPLICABLE"), (40, False, "APPLICABLE"), (39, False, "NOT_APPLICABLE"),
])
def test_factory_status_thresholds_authoritative(engine, workers, power, expected):
    assert prod(engine, "REQ-0005", {WC: workers, PWR: power}) == expected


def test_rule_0008_remains_draft_and_not_approved(dataset):
    assert dataset.rule_versions["RULE-0008-V1"]["status"] == "DRAFT"
    assert not any(v["target_id"] == "RULE-0008-V1" for v in dataset.verifications.values())


# --- FSSAI --------------------------------------------------------------------------------------
@pytest.mark.parametrize("turnover, expected", [
    (int(1.5 * CR), ("NOT_APPLICABLE", "NOT_APPLICABLE", "APPLICABLE")),
    (int(1.5 * CR) + 1, ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")),
    (50 * CR, ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")),
    (50 * CR + 1, ("APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE")),
])
@pytest.mark.parametrize("sub", SAME_BANDS)
def test_fssai_standard_bands_authoritative(engine, sub, turnover, expected):
    assert tiers(engine, {IND: "FOOD", TO: turnover, SUB: sub}) == expected


@pytest.mark.parametrize("sub", ALWAYS_CENTRAL)
@pytest.mark.parametrize("turnover", [CR, 40 * CR, 60 * CR, None])
def test_fssai_always_central_independent_of_turnover(engine, sub, turnover):
    facts = {IND: "FOOD", SUB: sub}
    if turnover is not None:
        facts[TO] = turnover
    assert tiers(engine, facts) == ("APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE")


@pytest.mark.parametrize("turnover", [CR, 40 * CR, 60 * CR, None])
def test_fssai_milling_is_state_independent_of_turnover(engine, turnover):
    facts = {IND: "FOOD", SUB: "GRAIN_CEREAL_PULSE_MILLING"}
    if turnover is not None:
        facts[TO] = turnover
    assert tiers(engine, facts) == ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")


@pytest.mark.parametrize("industry", NON_FOOD)
def test_fssai_non_food_industries_authoritative_not_applicable(engine, industry):
    assert tiers(engine, {IND: industry}) == ("NOT_APPLICABLE",) * 3


def test_fssai_unknown_industry_requires_information(engine):
    for req in ("REQ-0011", "REQ-0012", "REQ-0013"):
        assert prod(engine, req, {}) == "REQUIRES_INFORMATION"
    # a tier the facts already rule out stays NOT_APPLICABLE even with industry unknown (Kleene AND with FALSE)
    assert prod(engine, "REQ-0012", {TO: 40 * CR, SUB: "OTHER_FOOD_PROCESSING"}) == "REQUIRES_INFORMATION"
    assert prod(engine, "REQ-0011", {TO: 40 * CR, SUB: "OTHER_FOOD_PROCESSING"}) == "NOT_APPLICABLE"


# --- still fail-closed ---------------------------------------------------------------------------
@pytest.mark.parametrize("req", ["REQ-0001", "REQ-0004"])
def test_water_and_req0004_remain_blocked_in_production(engine, req):
    facts = {IND: "FOOD", TO: 40 * CR, SUB: "OTHER_FOOD_PROCESSING", "project.likely_to_discharge_sewage_or_trade_effluent": True}
    assert engine.evaluate_requirement("P", req, facts, PROD)["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


@pytest.mark.parametrize("rvid", ["RULE-0014-V2", "RULE-0015-V2", "RULE-0016-V1", "RULE-0014-V1", "RULE-0015-V1"])
def test_superseded_fssai_versions_never_authoritative(dataset, rvid):
    assert dataset.rule_versions[rvid]["status"] == "SUPERSEDED"
    for mode in (PROD, NP):
        assert evaluate_rule_version(rvid, dataset, {IND: "FOOD", TO: 40 * CR}, mode).blocked is True


def test_all_seventeen_active_versions_valid_and_approved(dataset):
    active = {k for k, v in dataset.rule_versions.items() if v["status"] == "ACTIVE"}
    assert active == BATCH1_ACTIVE | BATCH2_ACTIVE
    for rv in active:
        assert any(v["target_id"] == rv and v["result"] == "APPROVED" and v["reviewer"] == "Hardik Trivedi"
                   for v in dataset.verifications.values()), rv
    report = validate_dataset(dataset.root, dataset)
    assert report.active_promotion_violations == []


def test_batch2_supporting_evidence_and_facts_are_verified_and_unrelated_ones_are_not(dataset):
    for e in ("EVID-MPCB-02", "EVID-MPCB-05", "EVID-MPCB-06", "EVID-MPCB-07", "EVID-OSH-01", "EVID-OSH-02",
              "EVID-OSH-03", "EVID-OSH-04", "EVID-FSS-07", "EVID-FSS-08"):
        assert dataset.evidence[e]["verification_status"] == "VERIFIED", e
    for f in ("RF-0002", "RF-0035", "RF-0014", "RF-0015", "RF-0022", "RF-0023", "RF-0024"):
        assert dataset.facts[f]["verification_status"] == "VERIFIED", f
    for e in ("EVID-MPCB-03", "EVID-MPCB-04", "EVID-FSS-06"):
        assert dataset.evidence[e]["verification_status"] == "UNVERIFIED", e
    for f in ("RF-0034", "RF-0013"):
        assert dataset.facts[f]["verification_status"] == "UNVERIFIED", f


def test_diagnostic_mode_still_functional(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True,
                                                       WHITE: False, PEC: False}, NP)
    assert d["final_state"] == "APPLICABLE" and d["is_non_production_result"] is True
    d4 = engine.evaluate_requirement("P", "REQ-0004", {IND: "FOOD"}, NP)
    assert d4["is_non_production_result"] is True and not d4["final_state"].startswith("BLOCKED")
