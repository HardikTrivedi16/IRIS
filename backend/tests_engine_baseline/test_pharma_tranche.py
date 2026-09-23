"""
Pharma tranche (PH-01/02/03/04/05) — MH_MULTI_SECTOR_REGULATORY_RESEARCH.md
§7/§12/H1/H2.2/H6. See regulatory-data/registers/rule_review_register.yaml
RULE-REV-0002 for the full engineering rationale behind REQ-0003's
coarse-gate + classification_rule_ids restructuring (PH-01/02/03) and the
identical pattern under new REQ-0014 (PH-04).

Every Rule Version here is DRAFT — PRODUCTION-mode calls are expected to
return BLOCKED_DRAFT_NOT_PRODUCTION; NON_PRODUCTION (diagnostic) mode is
used throughout to exercise the actual condition logic.
"""
from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION

_DRUG_GATE = {
    "project.manufactures_drugs_for_sale_or_distribution": True,
    "project.pharma_activity_type": "FORMULATIONS",
}


def _facts(schedule):
    f = dict(_DRUG_GATE)
    f["project.drug_schedule_classification"] = schedule
    return f


# --- A. missing drug_schedule_classification -------------------------------

def test_missing_schedule_requires_information(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", dict(_DRUG_GATE), NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


# --- B. NONE -> PH-01 (Form 24/25) ------------------------------------------

def test_schedule_none_is_ph01_form_24(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", _facts("NONE"), NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0017"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0018"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0019"] == "NOT_APPLICABLE"


# --- C. SCHEDULE_C_OR_C1 -> PH-02 (Form 27/28) ------------------------------

def test_schedule_c_or_c1_is_ph02_form_27(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", _facts("SCHEDULE_C_OR_C1"), NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0018"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0017"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0019"] == "NOT_APPLICABLE"


# --- D. SCHEDULE_X_ONLY -> PH-03 (Form 24-F/25-F) ---------------------------

def test_schedule_x_only_is_ph03_form_24f(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", _facts("SCHEDULE_X_ONLY"), NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0019"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0017"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0018"] == "NOT_APPLICABLE"


# --- E. SCHEDULE_C_OR_C1_AND_X -> PH-03 combined (Form 27-B/28-B) -----------

def test_schedule_c_or_c1_and_x_is_ph03_form_27b(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", _facts("SCHEDULE_C_OR_C1_AND_X"), NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0019"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0017"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0018"] == "NOT_APPLICABLE"


def test_ph01_ph02_ph03_are_mutually_exclusive_no_overlap_review(engine):
    # None of the four ENUM values should ever trip the classification
    # module's UNREGISTERED_OVERLAP/UNDETERMINED_OVERLAP branch — the
    # branches are constructed to be genuinely mutually exclusive.
    for schedule in ("NONE", "SCHEDULE_C_OR_C1", "SCHEDULE_X_ONLY", "SCHEDULE_C_OR_C1_AND_X"):
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        assert d["final_state"] == "APPLICABLE", schedule
        assert d["review_reason"] is None, schedule


# --- old dead-end must not resurface ----------------------------------------

def test_requires_review_dead_end_no_longer_reachable(engine):
    # Prior to the correction, an excluded-schedule value dead-ended at
    # REQUIRES_REVIEW (RULE-REV-0002). All four known ENUM values must now
    # resolve to a definite APPLICABLE answer via classification.
    for schedule in ("NONE", "SCHEDULE_C_OR_C1", "SCHEDULE_X_ONLY", "SCHEDULE_C_OR_C1_AND_X"):
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        assert d["final_state"] != "REQUIRES_REVIEW", schedule


# --- F. pharma_activity_type branch behavior --------------------------------

def test_repacking_activity_fails_the_coarse_gate(engine):
    facts = {
        "project.manufactures_drugs_for_sale_or_distribution": True,
        "project.pharma_activity_type": "REPACKING",
        "project.drug_schedule_classification": "NONE",
    }
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    assert d["final_state"] == "NOT_APPLICABLE"


def test_not_manufacturing_for_sale_fails_the_coarse_gate(engine):
    facts = {
        "project.manufactures_drugs_for_sale_or_distribution": False,
        "project.pharma_activity_type": "FORMULATIONS",
        "project.drug_schedule_classification": "NONE",
    }
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    assert d["final_state"] == "NOT_APPLICABLE"


# --- PH-04: pharma_activity_type + location classification -----------------

def test_ph04_formulations_not_applicable(engine):
    facts = {
        "project.pharma_activity_type": "FORMULATIONS",
        "project.located_in_notified_industrial_area": False,
    }
    d = engine.evaluate_requirement("P", "REQ-0014", facts, NP)
    assert d["final_state"] == "NOT_APPLICABLE"


def test_ph04_bulk_drug_outside_notified_area_is_category_a(engine):
    facts = {
        "project.pharma_activity_type": "BULK_DRUG_OR_INTERMEDIATE",
        "project.located_in_notified_industrial_area": False,
    }
    d = engine.evaluate_requirement("P", "REQ-0014", facts, NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0021"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0022"] == "NOT_APPLICABLE"


def test_ph04_bulk_drug_inside_notified_area_is_category_b(engine):
    facts = {
        "project.pharma_activity_type": "BULK_DRUG_OR_INTERMEDIATE",
        "project.located_in_notified_industrial_area": True,
    }
    d = engine.evaluate_requirement("P", "REQ-0014", facts, NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0022"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0021"] == "NOT_APPLICABLE"


def test_ph04_bulk_drug_unknown_location_requires_information(engine):
    facts = {"project.pharma_activity_type": "BULK_DRUG_OR_INTERMEDIATE"}
    d = engine.evaluate_requirement("P", "REQ-0014", facts, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


# --- PH-05: retention obligation --------------------------------------------

def test_ph05_holds_licence_retention_applies(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0015", {"project.holds_drug_manufacturing_licence": True}, NP
    )
    assert d["final_state"] == "APPLICABLE"


def test_ph05_no_licence_retention_not_applicable(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0015", {"project.holds_drug_manufacturing_licence": False}, NP
    )
    assert d["final_state"] == "NOT_APPLICABLE"


def test_ph05_unknown_requires_information(engine):
    d = engine.evaluate_requirement("P", "REQ-0015", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


# --- G. DRAFT Pharma Rule Versions blocked in PRODUCTION --------------------

def test_new_pharma_requirements_stay_draft_and_non_authoritative_in_production(engine):
    for req_id in ("REQ-0003", "REQ-0014", "REQ-0015"):
        d = engine.evaluate_requirement("P", req_id, {}, PROD)
        assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION", req_id


# --- H. historical/superseded cannot become current authoritative output ---

def test_repurposed_rule_0003_is_the_latest_and_only_version(dataset):
    # RULE-0003 was corrected in place (never ACTIVE, so no SUPERSEDED
    # history was created for it) — confirm it is still the sole, current
    # version the index points at, and that no stray second version exists.
    assert dataset.latest_rule_version_id("RULE-0003") == "RULE-0003-V1"
    versions_for_rule_0003 = [
        rv for rv in dataset.rule_versions.values() if rv.get("rule_id") == "RULE-0003"
    ]
    assert len(versions_for_rule_0003) == 1
    assert versions_for_rule_0003[0]["status"] == "DRAFT"


def test_unrelated_fssai_superseded_versions_still_cannot_surface(engine, dataset):
    # Sanity check that this tranche did not accidentally touch the
    # FSSAI currentness work's lifecycle guarantees (RULE-REV-0006):
    # RULE-0014-V1/RULE-0015-V1 must remain SUPERSEDED and unreachable as
    # the current answer for REQ-0011/REQ-0012.
    assert dataset.rule_versions["RULE-0014-V1"]["status"] == "SUPERSEDED"
    assert dataset.rule_versions["RULE-0015-V1"]["status"] == "SUPERSEDED"
    assert dataset.latest_rule_version_id("RULE-0014") == "RULE-0014-V2"
    assert dataset.latest_rule_version_id("RULE-0015") == "RULE-0015-V2"


# --- authority correction ----------------------------------------------------

def test_req_0003_authority_is_fda_mh_not_cdsco(dataset):
    req = dataset.requirements["REQ-0003"]
    assert req["authority_id"] == "AUTH-FDA-MH"
    assert "AUTH-FDA-MH" in dataset.authorities
    assert "AUTH-CDSCO" in dataset.authorities


# --- fact registry: new pharma keys are correctly derived -------------------

def test_pharma_facts_registered_generically(dataset):
    from app.fact_registry import fact_registry_index

    registry = fact_registry_index()
    for key in (
        "project.drug_schedule_classification",
        "project.pharma_activity_type",
        "project.manufactures_drugs_for_sale_or_distribution",
        "project.holds_drug_manufacturing_licence",
        "project.located_in_notified_industrial_area",
    ):
        assert key in registry, key
        assert registry[key]["consumer_domains"] == ["REGULATORY"], key

    schedule_entry = registry["project.drug_schedule_classification"]
    assert schedule_entry["value_type"] == "string"
    assert set(schedule_entry["values_referenced_by_conditions"]) == {
        "NONE", "SCHEDULE_C_OR_C1", "SCHEDULE_X_ONLY", "SCHEDULE_C_OR_C1_AND_X",
    }

    activity_entry = registry["project.pharma_activity_type"]
    assert set(activity_entry["values_referenced_by_conditions"]) >= {
        "BULK_DRUG_OR_INTERMEDIATE",
    }
