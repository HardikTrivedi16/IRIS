"""
Batch 2b - verification candidates REQ-0001, 0002, 0004, 0005, 0011, 0012, 0013 (+ Pharma date-metadata check).

Everything stays DRAFT / UNVERIFIED. These tests pin the FSSAI full-carve-out guard (RULE-0014-V3/0015-V3/0016-V2),
the OSH archived-artifact checksums, the REQ-0005 provenance chain, that no Batch-2b candidate is authoritative in
Production, and that the Pharma effective-date clarification is metadata-only.
"""
import hashlib
import os

import pytest

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

T = "project.annual_turnover_inr"
SUB = "project.food_subsector"
CRORE = 10_000_000

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")
REPO_ROOT = os.path.dirname(os.path.dirname(DATA_ROOT))

SAME_BANDS = ["OTHER_FOOD_PROCESSING", "DAIRY", "VEGETABLE_OIL", "SLAUGHTER", "MEAT_PROCESSING", "FISH_PRODUCTS",
              "SUBSTANCES_ADDED_TO_FOOD"]
ALWAYS_CENTRAL = ["HEALTH_SUPPLEMENT_NUTRACEUTICAL", "AYURVEDA_AAHARA", "PROPRIETARY_FOOD", "NON_SPECIFIED_FOOD",
                  "RADIATION_PROCESSING", "EXPORT_ORIENTED_OR_EXPORTER_MANUFACTURER"]
MILLING = "GRAIN_CEREAL_PULSE_MILLING"
IND = "project.industry"
NON_FOOD = ["PHARMACEUTICAL", "AUTOMOBILE_EV", "ELECTRONICS_ESDM", "CHEMICALS"]  # canonical values seeded on the showcase projects


def state(engine, req, facts, mode=NP):
    return engine.evaluate_requirement("P", req, facts, mode)["final_state"]


def tiers(engine, facts):
    return tuple(state(engine, r, facts) for r in ("REQ-0011", "REQ-0012", "REQ-0013"))  # Central, State, Registration


@pytest.mark.parametrize("turnover, expected", [
    (int(1.5 * CRORE), ("NOT_APPLICABLE", "NOT_APPLICABLE", "APPLICABLE")),       # Rs 1.5 crore exactly -> Registration
    (int(1.5 * CRORE) + 1, ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")),   # just above -> State
    (50 * CRORE, ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")),             # Rs 50 crore exactly -> State
    (50 * CRORE + 1, ("APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE")),         # just above -> Central
    (40 * CRORE, ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")),
    (60 * CRORE, ("APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE")),
])
@pytest.mark.parametrize("sub", SAME_BANDS)
def test_same_band_subsectors_follow_the_turnover_bands(engine, sub, turnover, expected):
    assert tiers(engine, {IND: "FOOD", T: turnover, SUB: sub}) == expected


@pytest.mark.parametrize("sub", ALWAYS_CENTRAL)
@pytest.mark.parametrize("turnover", [CRORE, 40 * CRORE, 60 * CRORE, None])
def test_always_central_categories_are_central_regardless_of_turnover(engine, sub, turnover):
    facts = {IND: "FOOD", SUB: sub}
    if turnover is not None:
        facts[T] = turnover
    assert tiers(engine, facts) == ("APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE")


@pytest.mark.parametrize("turnover", [CRORE, 40 * CRORE, 60 * CRORE, None])
def test_milling_units_are_state_regardless_of_turnover(engine, turnover):
    facts = {IND: "FOOD", SUB: MILLING}
    if turnover is not None:
        facts[T] = turnover
    assert tiers(engine, facts) == ("NOT_APPLICABLE", "APPLICABLE", "NOT_APPLICABLE")


@pytest.mark.parametrize("industry", NON_FOOD)
def test_non_food_industries_are_not_applicable_never_requires_information(engine, industry):
    # no turnover / subsector facts at all: must not ask a non-food project for FSSAI information
    assert tiers(engine, {IND: industry}) == ("NOT_APPLICABLE",) * 3
    assert tiers(engine, {IND: industry, T: 60 * CRORE, SUB: "OTHER_FOOD_PROCESSING"}) == ("NOT_APPLICABLE",) * 3


def test_food_industry_gate_lets_classification_proceed(engine):
    # FOOD with nothing else known still asks for the FSSAI facts
    r = engine.evaluate_requirement("P", "REQ-0012", {IND: "FOOD"}, NP)
    assert r["final_state"] == "REQUIRES_INFORMATION"
    assert {SUB, T} <= set(r["missing_project_fact_keys"])
    # industry itself unknown is never assumed non-food
    assert state(engine, "REQ-0012", {T: 40 * CRORE, SUB: "OTHER_FOOD_PROCESSING"}) == "REQUIRES_INFORMATION"


def test_industry_gate_reuses_the_canonical_fact_and_no_duplicate_fact(dataset):
    for rid in ("RULE-0014-V3", "RULE-0015-V3", "RULE-0016-V2"):
        assert "project.industry" in dataset.rule_versions[rid]["required_project_facts"]
    keys = {c.get("target_variable_key") for c in dataset.conditions.values()}
    assert not any(k and "food_industry" in k for k in keys)


def test_fssai_successor_chain_and_status(dataset):
    for new, old in (("RULE-0014-V3", "RULE-0014-V2"), ("RULE-0015-V3", "RULE-0015-V2"),
                     ("RULE-0016-V2", "RULE-0016-V1")):
        assert dataset.rule_versions[new]["supersedes_rule_version_id"] == old
        assert dataset.rule_versions[new]["status"] == "ACTIVE"  # approved in Verification Batch 2
        assert dataset.rule_versions[old]["status"] == "SUPERSEDED"
        assert dataset.rule_versions[new]["effective_start_date"] == "2026-04-01"
    # the historical guard is preserved unchanged for the superseded versions
    assert len(dataset.conditions["COND-0032"]["comparison_value"]) == 5
    assert len(dataset.conditions["COND-0082"]["comparison_value"]) == 7


def test_superseded_fssai_versions_are_not_authoritative_in_production(dataset, engine):
    from iris_engine.rules import evaluate_rule_version
    for rvid in ("RULE-0014-V2", "RULE-0015-V2", "RULE-0016-V1"):
        ev = evaluate_rule_version(rvid, dataset, {IND: "FOOD", T: 40 * CRORE, SUB: "OTHER_FOOD_PROCESSING"}, evaluation_mode=PROD)
        assert ev.blocked, rvid


def test_active_rules_are_exactly_the_approved_batch1_and_batch2_versions(dataset):
    active = {k for k, v in dataset.rule_versions.items() if v["status"] == "ACTIVE"}
    assert active == {"RULE-0003-V1", "RULE-0009-V1", "RULE-0010-V1", "RULE-0012-V2", "RULE-0013-V2", "RULE-0017-V1",
                      "RULE-0018-V1", "RULE-0019-V1", "RULE-0023-V1", "RULE-0025-V2", "RULE-0026-V2", "RULE-0027-V2",
                      "RULE-0002-V2", "RULE-0007-V1", "RULE-0014-V3", "RULE-0015-V3", "RULE-0016-V2"}


def test_req0004_is_marked_not_authoritative_and_stays_draft(dataset):
    req = dataset.requirements["REQ-0004"]
    assert "NOT THE AUTHORITATIVE FSSAI CLASSIFICATION RESULT" in req["deprecation_note"]
    assert dataset.rule_versions["RULE-0004-V1"]["status"] == "DRAFT"


def test_dish_faq_is_not_labelled_as_a_gazette(dataset):
    src = dataset.sources["SRC-034"]
    assert src["document_type"] == "OFFICIAL_WEBSITE" and src["source_status"] == "AVAILABLE"
    assert src["archived_artifact_path"] is None and src["checksum_sha256"] is None
    assert dataset.evidence["EVID-OSH-02"]["source_id"] == "SRC-034"
    assert "SRC-034" in dataset.rule_versions["RULE-0007-V1"]["source_ids"]
    assert "SRC-006" not in dataset.rule_versions["RULE-0007-V1"]["source_ids"]


def test_unapproved_batch2b_candidates_stay_blocked_in_production(engine):
    facts = {IND: "FOOD", T: 40 * CRORE, SUB: "OTHER_FOOD_PROCESSING", "project.worker_count": 46,
             "project.manufacturing_process_uses_power": True}
    for req in ("REQ-0001", "REQ-0004"):
        assert state(engine, req, facts, PROD).startswith("BLOCKED"), req


def test_diagnostic_mode_still_evaluates_factory_status(engine):
    f = {"project.worker_count": 46, "project.manufacturing_process_uses_power": True}
    assert state(engine, "REQ-0005", f) == "APPLICABLE"
    assert state(engine, "REQ-0005", {"project.worker_count": 19, "project.manufacturing_process_uses_power": True}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0005", {"project.worker_count": 39, "project.manufacturing_process_uses_power": False}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0005", {"project.worker_count": 40, "project.manufacturing_process_uses_power": False}) == "APPLICABLE"


def test_air_prior_ec_stays_applicable_for_consent_to_operate(engine):
    base = {"project.plant_located_in_air_pollution_control_area": True, "project.is_white_category_industrial_plant": False}
    assert state(engine, "REQ-0002", dict(base, **{"project.holds_prior_environmental_clearance": True})) == "APPLICABLE"
    assert state(engine, "REQ-0002", dict(base, **{"project.is_white_category_industrial_plant": True})) == "NOT_APPLICABLE"


@pytest.mark.parametrize("name, sha", [
    ("SRC-032_OSH_Code_2020_Act37_LabourMin.pdf", "9ce8f68b88f725fbce4fadfb45d9ddc3ed7a5f59d92a2ebd3d5bd7ebb1c83891"),
    ("SRC-033_OSH_Code_Commencement_SO5321E_21Nov2025_Gazette.pdf", "22212bc1f9e601ad242c9c595fd5ae91382b6c8ed8085c921f384343e1a8d642"),
])
def test_osh_archived_artifact_checksums(dataset, name, sha):
    with open(os.path.join(DATA_ROOT, "archive", name), "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha
    src = dataset.sources[name.split("_")[0]]
    assert src["checksum_sha256"] == sha
    assert src["source_status"] == "ARCHIVED"
    assert os.path.exists(os.path.join(REPO_ROOT, src["archived_artifact_path"]))


def test_req0005_provenance_chain_resolves(dataset):
    rv = dataset.rule_versions["RULE-0007-V1"]
    assert rv["status"] == "ACTIVE" and rv["effective_start_date"] == "2025-11-21"
    for rfid in rv["regulatory_fact_ids"]:
        rf = dataset.facts[rfid]
        for evid in rf["evidence_ids"]:
            assert dataset.evidence[evid]["source_id"] in dataset.sources
    assert {"SRC-032", "SRC-033"} <= set(rv["source_ids"])
    assert dataset.evidence["EVID-OSH-01"]["source_id"] == "SRC-032"
    assert dataset.evidence["EVID-OSH-03"]["source_id"] == "SRC-033"
    assert "ten or more workers" in dataset.evidence["EVID-OSH-04"]["excerpt"]
    assert "registration" in rv["false_outcome"].lower()


def test_water_v2_remains_without_invented_date(dataset):
    rv = dataset.rule_versions["RULE-0001-V2"]
    assert rv["effective_start_date"] is None and rv["status"] == "DRAFT"


def test_pharma_date_clarification_is_metadata_only(dataset):
    for rid in ("RULE-0003-V1", "RULE-0017-V1", "RULE-0018-V1", "RULE-0019-V1"):
        rv = dataset.rule_versions[rid]
        assert rv["status"] == "ACTIVE" and rv["effective_start_date"] == "2017-10-27"
        assert "NOT the origin of the manufacturing-licence pathways" in rv["approval_note"]
