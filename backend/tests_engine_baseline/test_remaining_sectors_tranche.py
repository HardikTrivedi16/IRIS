"""
Remaining-sector tranche (AU-01/AU-02, EL-01/EL-02, CH-02/CH-03) -
MH_MULTI_SECTOR_REGULATORY_RESEARCH.md §8-§10/§12/H2.2/H6. CH-01 has no
Requirement (RULE-REV-0007); CH-04/CH-05 are research-register-only
(RULE-REV-0008/0009).

Every Rule Version is DRAFT: PRODUCTION calls must return
BLOCKED_DRAFT_NOT_PRODUCTION; NON_PRODUCTION exercises the condition logic.
"""
import pytest

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

# requirement -> (fact key, rule id)
CASES = {
    "REQ-0016": "project.manufactures_motor_vehicles_for_sale",           # AU-01
    "REQ-0017": "project.places_batteries_on_market",                     # AU-02
    "REQ-0018": "project.sells_schedule1_eee_under_own_brand",            # EL-01
    "REQ-0019": "project.manufactures_schedule1_eee",                     # EL-02
    "REQ-0020": "project.msihc_schedule3_chemical_at_or_above_threshold", # CH-02
    "REQ-0021": "project.msihc_schedule3_chemical_at_or_above_threshold", # CH-03
}


@pytest.mark.parametrize("req_id,fact", sorted(CASES.items()))
def test_positive_negative_unknown(engine, req_id, fact):
    assert engine.evaluate_requirement("P", req_id, {fact: True}, NP)["final_state"] == "APPLICABLE"
    assert engine.evaluate_requirement("P", req_id, {fact: False}, NP)["final_state"] == "NOT_APPLICABLE"
    assert engine.evaluate_requirement("P", req_id, {}, NP)["final_state"] == "REQUIRES_INFORMATION"


@pytest.mark.parametrize("req_id", sorted(CASES))
def test_production_is_draft_blocked(engine, req_id):
    d = engine.evaluate_requirement("P", req_id, {CASES[req_id]: True}, PROD)
    assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


def test_sector_alone_never_triggers(engine):
    # Auto/EV, Electronics and Chemicals sector projects without the actual
    # trigger facts must not become APPLICABLE.
    for sector in ("AUTO", "EV", "ELECTRONICS", "CHEMICALS", "FOOD", "PHARMA"):
        facts = {"project.industry": sector, "project.sector": sector}
        for req_id in CASES:
            d = engine.evaluate_requirement("P", req_id, dict(facts), NP)
            assert d["final_state"] == "REQUIRES_INFORMATION", (sector, req_id)


def test_ep_and_ee_are_independent_requirements(engine):
    # producer-only vs manufacturer-only (H2.2: two Requirements, not one)
    d1 = engine.evaluate_requirement(
        "P", "REQ-0018", {"project.sells_schedule1_eee_under_own_brand": True,
                          "project.manufactures_schedule1_eee": False}, NP)
    d2 = engine.evaluate_requirement(
        "P", "REQ-0019", {"project.sells_schedule1_eee_under_own_brand": True,
                          "project.manufactures_schedule1_eee": False}, NP)
    assert d1["final_state"] == "APPLICABLE"
    assert d2["final_state"] == "NOT_APPLICABLE"


def test_food_and_pharma_projects_unaffected(engine):
    # A Food/Pharma project with no new trigger facts must not receive
    # any new requirement as APPLICABLE.
    for facts in (
        {"project.industry": "FOOD", "project.annual_turnover_inr": 20_000_000},
        {"project.manufactures_drugs_for_sale_or_distribution": True,
         "project.pharma_activity_type": "FORMULATIONS",
         "project.drug_schedule_classification": "NONE"},
    ):
        for req_id in CASES:
            d = engine.evaluate_requirement("P", req_id, dict(facts), NP)
            assert d["final_state"] != "APPLICABLE", req_id


def test_all_new_rule_versions_draft_and_unverified(dataset):
    for n in range(24, 30):
        rv = dataset.rule_versions[f"RULE-{n:04d}-V1"]
        assert rv["status"] == "DRAFT"


def test_au01_has_no_fabricated_grounding(dataset):
    rv = dataset.rule_versions["RULE-0024-V1"]
    assert rv["regulatory_fact_ids"] == [] and rv["evidence_ids"] == [] and rv["source_ids"] == []
    assert rv["confidence"] == "REQUIRES_REVIEW"


def test_new_sources_available_not_archived(dataset):
    for sid in ("SRC-015", "SRC-016", "SRC-017"):
        s = dataset.sources[sid]
        assert s["source_status"] == "AVAILABLE"
        assert s["archived_artifact_path"] is None and s["checksum_sha256"] is None


def test_ch01_ch04_ch05_are_not_executable(dataset):
    codes = " ".join(r["code"] for r in dataset.requirements.values()).upper()
    assert codes.count("EIA") == 1  # REQ-0014 (PH-04) only; no CH-01
    for needle in ("HAZARDOUS_PROCESS", "PESO"):
        assert needle not in codes
    from pathlib import Path
    import yaml
    reg = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "regulatory-data" / "registers" / "rule_review_register.yaml").read_text(encoding="utf-8")
    )
    ids = {i["review_id"] for i in reg["review_items"]}
    assert {"RULE-REV-0007", "RULE-REV-0008", "RULE-REV-0009"} <= ids


def test_dependency_edges_remain_zero(dataset):
    for req in dataset.requirements.values():
        assert req["dependencies_as_source"] == [] and req["dependencies_as_target"] == []


def test_new_facts_registered_generically():
    from app.fact_registry import fact_registry_index

    registry = fact_registry_index()
    for key in CASES.values():
        entry = registry[key]
        assert entry["value_type"] == "boolean", key
        assert entry["consumer_domains"] == ["REGULATORY"], key
