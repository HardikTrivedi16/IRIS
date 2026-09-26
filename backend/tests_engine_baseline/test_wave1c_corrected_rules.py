"""
Wave 1C — corrected DRAFT successor Rule Versions (RULE-0001-V2, RULE-0002-V2,
RULE-0012-V2, RULE-0013-V2) and Boilers commencement provenance.

Everything here is DRAFT / non-production: no VER record exists, nothing is
ACTIVE. These tests pin the deterministic boundaries of the corrected logic
and that the historical Rule Versions are preserved.
"""
import hashlib
import os

import pytest

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

DIS = "project.likely_to_discharge_sewage_or_trade_effluent"
APCA = "project.plant_located_in_air_pollution_control_area"
WHITE = "project.is_white_category_industrial_plant"
EC = "project.holds_prior_environmental_clearance"
LM_OLD = "project.prepacks_commodities_for_retail_sale"
LM_NEW = "project.prepacks_or_imports_commodities_for_sale_distribution_or_delivery"
WASTE = "project.generates_or_handles_scheduled_hazardous_waste"
CNR = "project.state_board_consent_not_required_under_water_and_air_acts"
HAND = "project.hands_over_hazardous_waste_to_authorised_actual_user_collector_or_disposal_facility"

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")


def state(engine, req, facts):
    return engine.evaluate_requirement("P", req, facts, NP)["final_state"]


# --- REQ-0001 (Water CTE): normal trigger vs White vs prior-EC ----------------

def test_water_normal_trigger_applies(engine):
    assert state(engine, "REQ-0001", {DIS: True, WHITE: False, EC: False}) == "APPLICABLE"


def test_water_white_category_exempt(engine):
    assert state(engine, "REQ-0001", {DIS: True, WHITE: True, EC: False}) == "NOT_APPLICABLE"


def test_water_prior_ec_exempt_from_consent_to_establish(engine):
    assert state(engine, "REQ-0001", {DIS: True, WHITE: False, EC: True}) == "NOT_APPLICABLE"


def test_water_exemption_holds_even_if_discharge_unknown(engine):
    assert state(engine, "REQ-0001", {WHITE: True}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0001", {EC: True}) == "NOT_APPLICABLE"


def test_water_no_discharge_not_applicable(engine):
    assert state(engine, "REQ-0001", {DIS: False}) == "NOT_APPLICABLE"


def test_water_missing_exemption_facts_never_assumed_false(engine):
    # A likely discharger who has not said whether White/prior-EC applies is
    # REQUIRES_INFORMATION - neither APPLICABLE nor silently exempt.
    assert state(engine, "REQ-0001", {DIS: True}) == "REQUIRES_INFORMATION"
    assert state(engine, "REQ-0001", {DIS: True, WHITE: False}) == "REQUIRES_INFORMATION"
    assert state(engine, "REQ-0001", {}) == "REQUIRES_INFORMATION"


# --- REQ-0002 (Air CTE/CTO): normal trigger vs White; EC CTE/CTO distinction --

def test_air_normal_trigger_applies(engine):
    assert state(engine, "REQ-0002", {APCA: True, WHITE: False}) == "APPLICABLE"


def test_air_white_category_exempt(engine):
    assert state(engine, "REQ-0002", {APCA: True, WHITE: True}) == "NOT_APPLICABLE"


def test_air_outside_control_area_not_applicable(engine):
    assert state(engine, "REQ-0002", {APCA: False}) == "NOT_APPLICABLE"


def test_air_missing_white_fact_requires_information(engine):
    assert state(engine, "REQ-0002", {APCA: True}) == "REQUIRES_INFORMATION"


def test_air_prior_ec_exempts_cte_only_so_requirement_stays_applicable(engine, dataset):
    # G.S.R. 702(E)(b): prior EC exempts consent to ESTABLISH only; consent to
    # OPERATE still applies. The combined Requirement therefore stays APPLICABLE
    # (never collapsed to NOT_APPLICABLE), and the EC fact is deliberately not
    # consumed by the Rule Version.
    d = engine.evaluate_requirement("P", "REQ-0002", {APCA: True, WHITE: False, EC: True}, NP)
    assert d["final_state"] == "APPLICABLE"
    assert EC not in dataset.rule_versions["RULE-0002-V2"]["required_project_facts"]
    assert EC not in d["explanation"]["input_facts_used"]
    assert "consent to operate" in dataset.rule_versions["RULE-0002-V2"]["true_outcome"].lower()


# --- REQ-0009 (Legal Metrology r.27): corrected fact drives the rule ----------

def test_lm_new_fact_drives_v2(engine):
    assert state(engine, "REQ-0009", {LM_NEW: True}) == "APPLICABLE"
    assert state(engine, "REQ-0009", {LM_NEW: False}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0009", {}) == "REQUIRES_INFORMATION"


def test_lm_old_retail_only_fact_no_longer_drives_current_v2(engine, dataset):
    assert LM_OLD not in dataset.rule_versions["RULE-0012-V2"]["required_project_facts"]
    # the old fact alone leaves the current rule undetermined ...
    assert state(engine, "REQ-0009", {LM_OLD: True}) == "REQUIRES_INFORMATION"
    # ... and it cannot override the new fact in either direction.
    assert state(engine, "REQ-0009", {LM_OLD: True, LM_NEW: False}) == "NOT_APPLICABLE"
    assert state(engine, "REQ-0009", {LM_OLD: False, LM_NEW: True}) == "APPLICABLE"


def test_lm_v1_preserved_historically(dataset):
    v1 = dataset.rule_versions["RULE-0012-V1"]
    assert v1["status"] == "SUPERSEDED"
    assert v1["required_project_facts"] == [LM_OLD]
    assert dataset.rule_versions["RULE-0012-V2"]["supersedes_rule_version_id"] == "RULE-0012-V1"


# --- REQ-0010 (HOWM): exemption only when BOTH conditions hold ----------------

def test_hazwaste_not_generated_not_applicable(engine):
    assert state(engine, "REQ-0010", {WASTE: False}) == "NOT_APPLICABLE"


def test_hazwaste_normal_case_applies_when_consent_required(engine):
    assert state(engine, "REQ-0010", {WASTE: True, CNR: False, HAND: True}) == "APPLICABLE"
    assert state(engine, "REQ-0010", {WASTE: True, CNR: False}) == "APPLICABLE"


def test_hazwaste_applies_when_handover_not_established(engine):
    assert state(engine, "REQ-0010", {WASTE: True, CNR: True, HAND: False}) == "APPLICABLE"
    assert state(engine, "REQ-0010", {WASTE: True, HAND: False}) == "APPLICABLE"


def test_hazwaste_exempt_only_when_both_exemption_conditions_true(engine):
    assert state(engine, "REQ-0010", {WASTE: True, CNR: True, HAND: True}) == "NOT_APPLICABLE"


def test_hazwaste_partial_exemption_facts_are_not_enough(engine):
    assert state(engine, "REQ-0010", {WASTE: True, CNR: True}) == "REQUIRES_INFORMATION"
    assert state(engine, "REQ-0010", {WASTE: True, HAND: True}) == "REQUIRES_INFORMATION"
    assert state(engine, "REQ-0010", {WASTE: True}) == "REQUIRES_INFORMATION"


def test_hazwaste_no_ec_holder_exemption_invented(engine, dataset):
    rv = dataset.rule_versions["RULE-0013-V2"]
    assert EC not in rv["required_project_facts"]
    # prior EC (CTE exempt, CTO still required) cannot by itself exempt the project
    assert state(engine, "REQ-0010", {WASTE: True, EC: True, HAND: True}) == "REQUIRES_INFORMATION"


def test_hazwaste_v1_preserved_with_history_dates(dataset):
    v1 = dataset.rule_versions["RULE-0013-V1"]
    v2 = dataset.rule_versions["RULE-0013-V2"]
    assert v1["status"] == "SUPERSEDED"
    assert v1["effective_end_date"] == "2019-03-04"
    assert v2["effective_start_date"] == "2019-03-05"
    assert v2["supersedes_rule_version_id"] == "RULE-0013-V1"
    # V1 is still the as-authored trigger (no 6(1A) exemption)
    assert v1["condition_expression_root_id"] == "COND-0030"
    assert v1["required_project_facts"] == [WASTE]


# --- Historical Water / Air Rule Versions are untouched ----------------------

@pytest.mark.parametrize("v1,root", [("RULE-0001-V1", "COND-0001"), ("RULE-0002-V1", "COND-0002")])
def test_water_air_v1_preserved(dataset, v1, root):
    rv = dataset.rule_versions[v1]
    assert rv["condition_expression_root_id"] == root
    assert rv["status"] == "DRAFT"
    assert rv["effective_start_date"] is None and rv["effective_end_date"] is None


def test_v2_versions_link_to_v1_and_have_no_invented_dates(dataset):
    for v2, v1 in (("RULE-0001-V2", "RULE-0001-V1"), ("RULE-0002-V2", "RULE-0002-V1"),
                   ("RULE-0012-V2", "RULE-0012-V1")):
        rv = dataset.rule_versions[v2]
        assert rv["supersedes_rule_version_id"] == v1
        # Maharashtra adoption (Water) is unresolved - no date is asserted for RULE-0001-V2 (Batch 2b: BLOCKED).
        # RULE-0012-V2 got 2011-04-01 in Verification Batch 1; RULE-0002-V2 got 2024-11-12 (G.S.R. 702(E),
        # archived SRC-019) in Batch 2b.
        expected = {"RULE-0012-V2": "2011-04-01", "RULE-0002-V2": "2024-11-12"}.get(v2)
        assert rv["effective_start_date"] == expected


# --- Nothing verified / ACTIVE; production fails closed ----------------------

def test_new_successors_draft_unverified_and_blocked_in_production(engine, dataset):
    # REQ-0001 (Water) is NOT approved (Maharashtra adoption blocker): still DRAFT and blocked in Production.
    assert dataset.rule_versions["RULE-0001-V2"]["status"] == "DRAFT"
    assert engine.evaluate_requirement("P", "REQ-0001", {}, PROD)["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    # RULE-0002-V2 (Air) was approved in Verification Batch 2, so its evidence/fact are VERIFIED; the Water-only
    # evidence/fact stay UNVERIFIED.
    assert dataset.rule_versions["RULE-0002-V2"]["status"] == "ACTIVE"
    for evid in ("EVID-MPCB-03", "EVID-MPCB-04"):
        assert dataset.evidence[evid]["verification_status"] == "UNVERIFIED"
    for evid in ("EVID-MPCB-05", "EVID-MPCB-06", "EVID-MPCB-07"):
        assert dataset.evidence[evid]["verification_status"] == "VERIFIED"
    assert dataset.facts["RF-0034"]["verification_status"] == "UNVERIFIED"
    assert dataset.facts["RF-0035"]["verification_status"] == "VERIFIED"
    # REQ-0009/REQ-0010 and Boilers were approved in Verification Batch 1.
    for rvid in ("RULE-0012-V2", "RULE-0013-V2"):
        assert dataset.rule_versions[rvid]["status"] == "ACTIVE"
    for evid in ("EVID-HW-02", "EVID-LM-02", "EVID-BOILER-03"):
        assert dataset.evidence[evid]["verification_status"] == "VERIFIED"


def test_new_facts_are_boolean_leaves_in_the_regulatory_data(dataset):
    keys = {WHITE, EC, LM_NEW, CNR, HAND}
    seen = {}
    for c in dataset.conditions.values():
        k = c.get("target_variable_key")
        if k in keys:
            assert c["predicate_type"] == "BOOLEAN_EQUALS", c["condition_id"]
            assert c["unresolved_behavior"] == "UNKNOWN"
            seen[k] = True
    assert set(seen) == keys


# --- Boilers commencement (REQ-0006 / REQ-0007) ------------------------------

def test_boiler_rule_versions_carry_commencement_provenance(dataset):
    for rvid in ("RULE-0009-V1", "RULE-0010-V1"):
        rv = dataset.rule_versions[rvid]
        assert rv["effective_start_date"] == "2025-05-01"
        assert rv["status"] == "ACTIVE"  # promoted in Verification Batch 1
        assert "RF-0037" in rv["regulatory_fact_ids"]
        assert "EVID-BOILER-03" in rv["evidence_ids"]
        assert "SRC-028" in rv["source_ids"]
    assert dataset.evidence["EVID-BOILER-03"]["source_id"] == "SRC-028"


@pytest.mark.parametrize("src", ["SRC-027", "SRC-028"])
def test_new_source_checksums_match_archived_bytes(dataset, src):
    rec = dataset.sources[src]
    path = os.path.join(os.path.dirname(os.path.dirname(DATA_ROOT)), rec["archived_artifact_path"])
    assert os.path.isfile(path)
    with open(path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == rec["checksum_sha256"]
