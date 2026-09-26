"""
Batch 2 - verification-candidate reconciliation (REQ-0003, 0006, 0007, 0009, 0010, 0015, 0017, 0018, 0019).

Everything stays DRAFT / UNVERIFIED. These tests pin the corrected E-Waste and Battery Rule Versions, the
corrected Drugs outcome text, the archived-artifact checksums, and that every candidate's provenance chain
(Rule Version -> Regulatory Fact -> Evidence -> Source -> Instrument -> Authority) resolves.
"""
import hashlib
import os

import pytest

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

OWN = "project.sells_schedule1_eee_under_own_brand"
IMP = "project.sells_imported_schedule1_eee_or_imports_used_schedule1_eee"
MFG = "project.manufactures_schedule1_eee"
MS = "project.msme_classification"
BAT = "project.places_batteries_on_market"

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")
REPO_ROOT = os.path.dirname(os.path.dirname(DATA_ROOT))

CANDIDATE_LATEST = {
    "REQ-0003": ["RULE-0003-V1", "RULE-0017-V1", "RULE-0018-V1", "RULE-0019-V1"],
    "REQ-0006": ["RULE-0009-V1"],
    "REQ-0007": ["RULE-0010-V1"],
    "REQ-0009": ["RULE-0012-V2"],
    "REQ-0010": ["RULE-0013-V2"],
    "REQ-0015": ["RULE-0023-V1"],
    "REQ-0017": ["RULE-0025-V2"],
    "REQ-0018": ["RULE-0026-V2"],
    "REQ-0019": ["RULE-0027-V2"],
}


def state(engine, req, facts):
    return engine.evaluate_requirement("P", req, facts, NP)["final_state"]


# --- E-Waste: producer (REQ-0018) ------------------------------------------------

def test_producer_own_brand_applies(engine):
    assert state(engine, "REQ-0018", {OWN: True, MS: "SMALL"}) == "APPLICABLE"


def test_producer_import_limb_applies_without_own_brand(engine):
    # r.3(1)(t)(iii)-(iv): offers to sell imported EEE / imports used EEE
    assert state(engine, "REQ-0018", {OWN: False, IMP: True, MS: "MEDIUM"}) == "APPLICABLE"


def test_producer_neither_limb_not_applicable(engine):
    assert state(engine, "REQ-0018", {OWN: False, IMP: False, MS: "SMALL"}) == "NOT_APPLICABLE"


def test_producer_missing_import_fact_never_assumed_false(engine):
    assert state(engine, "REQ-0018", {OWN: False, MS: "SMALL"}) == "REQUIRES_INFORMATION"


def test_producer_micro_enterprise_excluded_by_rule_2c(engine):
    assert state(engine, "REQ-0018", {OWN: True, MS: "MICRO"}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0018", {OWN: False, IMP: True, MS: "MICRO"}) == "NOT_APPLICABLE"


def test_producer_unknown_msme_requires_information(engine):
    assert state(engine, "REQ-0018", {OWN: True}) == "REQUIRES_INFORMATION"
    assert state(engine, "REQ-0018", {OWN: True, MS: "UNKNOWN"}) == "REQUIRES_INFORMATION"


# --- E-Waste: manufacturer (REQ-0019) ---------------------------------------------

def test_manufacturer_boundaries(engine):
    assert state(engine, "REQ-0019", {MFG: True, MS: "NOT_MSME"}) == "APPLICABLE"
    assert state(engine, "REQ-0019", {MFG: True, MS: "MICRO"}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0019", {MFG: False}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0019", {MFG: True}) == "REQUIRES_INFORMATION"


def test_producer_and_manufacturer_remain_distinct_requirements(engine, dataset):
    facts = {OWN: True, MFG: False, MS: "SMALL"}
    assert state(engine, "REQ-0018", facts) == "APPLICABLE"
    assert state(engine, "REQ-0019", facts) == "NOT_APPLICABLE"
    assert dataset.requirements["REQ-0018"]["evaluated_by_rule_id"] != dataset.requirements["REQ-0019"]["evaluated_by_rule_id"]


def test_ewaste_v1_preserved_superseded(dataset):
    for v1, root in (("RULE-0026-V1", "COND-0064"), ("RULE-0027-V1", "COND-0065")):
        rv = dataset.rule_versions[v1]
        assert rv["status"] == "SUPERSEDED" and rv["condition_expression_root_id"] == root
    assert dataset.rule_versions["RULE-0026-V2"]["effective_start_date"] == "2023-04-01"


# --- Battery (REQ-0017) -----------------------------------------------------------

def test_battery_v2_logic_and_dates(engine, dataset):
    assert state(engine, "REQ-0017", {BAT: True}) == "APPLICABLE"
    assert state(engine, "REQ-0017", {BAT: False}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0017", {}) == "REQUIRES_INFORMATION"
    v1, v2 = dataset.rule_versions["RULE-0025-V1"], dataset.rule_versions["RULE-0025-V2"]
    assert v1["status"] == "SUPERSEDED" and v1["effective_end_date"] == "2023-10-24"
    assert v2["effective_start_date"] == "2023-10-25" and v2["supersedes_rule_version_id"] == "RULE-0025-V1"
    assert "contract assembler" in v2["false_outcome"].lower()  # the 2023 sub-clause (iv) caveat is stated


# --- Drugs: corrected outcome text / retention basis --------------------------------

def test_drug_pathway_text_no_longer_claims_renewal(dataset):
    for rvid in ("RULE-0017-V1", "RULE-0018-V1"):
        assert "grant or renewal" not in dataset.rule_versions[rvid]["true_outcome"].lower()
    assert "Form 27D" in dataset.rule_versions["RULE-0018-V1"]["true_outcome"]


def test_drug_classification_pathways_unchanged(engine):
    gate = {"project.manufactures_drugs_for_sale_or_distribution": True, "project.pharma_activity_type": "FORMULATIONS"}
    for cls in ("NONE", "SCHEDULE_C_OR_C1"):
        assert state(engine, "REQ-0003", dict(gate, **{"project.drug_schedule_classification": cls})) == "APPLICABLE"
    assert state(engine, "REQ-0003", dict(gate, **{"project.pharma_activity_type": "REPACKING"})) == "NOT_APPLICABLE"


def test_retention_rule_grounded_in_rules_72_73aa_77(dataset):
    rv = dataset.rule_versions["RULE-0023-V1"]
    assert "EVID-DRUGS-05" in rv["evidence_ids"] and "SRC-013" in rv["source_ids"]
    assert "Forms 25, 25A, 25B, 25F, 28, 28B and 28D" in dataset.facts["RF-0028"]["statement"]


# --- Archived artifacts: real checksums ----------------------------------------------

@pytest.mark.parametrize("sid", ["SRC-013", "SRC-014", "SRC-015", "SRC-016", "SRC-029", "SRC-030", "SRC-031"])
def test_archived_source_checksums_match_bytes(dataset, sid):
    rec = dataset.sources[sid]
    assert rec["source_status"] == "ARCHIVED"
    p = os.path.join(REPO_ROOT, rec["archived_artifact_path"])
    assert os.path.isfile(p)
    with open(p, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == rec["checksum_sha256"]


# --- Provenance chain for all 9 candidates -------------------------------------------

def test_provenance_chain_resolves_for_every_candidate(dataset):
    for req_id, rvids in CANDIDATE_LATEST.items():
        for rvid in rvids:
            rv = dataset.rule_versions[rvid]
            assert rv["status"] == "ACTIVE", rvid  # promoted in Verification Batch 1
            assert rv["regulatory_fact_ids"], rvid
            for rfid in rv["regulatory_fact_ids"]:
                rf = dataset.facts[rfid]
                assert rf["evidence_ids"], rfid
                for evid in rf["evidence_ids"]:
                    ev = dataset.evidence[evid]
                    assert ev["verification_status"] == "VERIFIED", evid
                    assert ev["source_id"] in dataset.sources, evid
            for sid in rv["source_ids"]:
                assert sid in dataset.sources
            assert rv["instrument_id"] in dataset.instruments, rvid
            assert rv["authority_id"] in dataset.authorities, rvid
    approved = {v["target_id"] for v in dataset.verifications.values() if v["result"] == "APPROVED"}
    assert {rv for rvs in CANDIDATE_LATEST.values() for rv in rvs} <= approved


def test_candidate_latest_versions_are_the_proposed_ones(dataset):
    for req_id, rvids in CANDIDATE_LATEST.items():
        req = dataset.requirements[req_id]
        assert dataset.latest_rule_version_id(req["evaluated_by_rule_id"]) == rvids[0]
        for extra in rvids[1:]:
            assert extra.split("-V")[0] in req.get("classification_rule_ids", [])
    # all nine are authoritative in Production now (empty facts -> REQUIRES_INFORMATION, not blocked)
    from iris_engine import Engine
    eng = Engine(dataset)
    for req_id in CANDIDATE_LATEST:
        assert eng.evaluate_requirement("P", req_id, {}, PROD)["final_state"] == "REQUIRES_INFORMATION", req_id
