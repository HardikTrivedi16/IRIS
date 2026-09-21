"""
Phase 8 §5 — test every current Rule Version (RULE-0001-V1 .. RULE-0006-V1)
directly via evaluate_rule_version, for its TRUE / FALSE / UNKNOWN paths,
confirming output_mapping is read from the Rule Version's own YAML (not
hard-coded), and that provenance/status fields come through correctly.
Rules are NOT assumed to share identical semantics (RULE-0003 in particular
maps FALSE -> REQUIRES_REVIEW, not NOT_APPLICABLE).
"""
from iris_engine.rules import evaluate_rule_version, EvaluationMode

NP = EvaluationMode.NON_PRODUCTION


def test_rule_0001_v1_all_three_paths(dataset):
    r = evaluate_rule_version("RULE-0001-V1", dataset,
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    assert r.final_state == "APPLICABLE"
    assert r.kleene_result.value == "TRUE"
    assert r.outcome_text.strip().startswith("APPLICABLE")

    r = evaluate_rule_version("RULE-0001-V1", dataset,
        {"project.likely_to_discharge_sewage_or_trade_effluent": False}, NP)
    assert r.final_state == "NOT_APPLICABLE"
    assert r.kleene_result.value == "FALSE"

    r = evaluate_rule_version("RULE-0001-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"
    assert r.kleene_result.value == "UNKNOWN"
    assert r.missing_fact_keys == ["project.likely_to_discharge_sewage_or_trade_effluent"]


def test_rule_0002_v1_all_three_paths(dataset):
    r = evaluate_rule_version("RULE-0002-V1", dataset,
        {"project.plant_located_in_air_pollution_control_area": True}, NP)
    assert r.final_state == "APPLICABLE"

    r = evaluate_rule_version("RULE-0002-V1", dataset,
        {"project.plant_located_in_air_pollution_control_area": False}, NP)
    assert r.final_state == "NOT_APPLICABLE"

    r = evaluate_rule_version("RULE-0002-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"


def test_rule_0003_v1_asymmetric_semantics(dataset):
    # TRUE path
    r = evaluate_rule_version("RULE-0003-V1", dataset,
        {"project.drug_schedule_classification": "GENERAL_SCHEDULE"}, NP)
    assert r.final_state == "APPLICABLE"
    # FALSE path -> REQUIRES_REVIEW (NOT NOT_APPLICABLE) -- this rule differs
    # from RULE-0001/0002/0004/0005/0006's FALSE->NOT_APPLICABLE mapping.
    r = evaluate_rule_version("RULE-0003-V1", dataset,
        {"project.drug_schedule_classification": "SCHEDULE_C"}, NP)
    assert r.final_state == "REQUIRES_REVIEW"
    assert r.final_state != "NOT_APPLICABLE"
    # UNKNOWN path
    r = evaluate_rule_version("RULE-0003-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"


def test_rule_0004_v1_all_three_paths(dataset):
    r = evaluate_rule_version("RULE-0004-V1", dataset, {"project.industry": "FOOD"}, NP)
    assert r.final_state == "APPLICABLE"
    r = evaluate_rule_version("RULE-0004-V1", dataset, {"project.industry": "PHARMA"}, NP)
    assert r.final_state == "NOT_APPLICABLE"
    r = evaluate_rule_version("RULE-0004-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"


def test_rule_0005_v1_all_three_paths(dataset):
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.dairy_liquid_milk_capacity": 60000, "project.dairy_milk_solids_capacity": 100}, NP)
    assert r.final_state == "APPLICABLE"
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.dairy_liquid_milk_capacity": 100, "project.dairy_milk_solids_capacity": 100}, NP)
    assert r.final_state == "NOT_APPLICABLE"
    r = evaluate_rule_version("RULE-0005-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"
    # partial info: one criterion known TRUE means the other need not be
    # collected (per the Rule Version's own engine_note) -> still APPLICABLE
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.dairy_liquid_milk_capacity": 60000}, NP)
    assert r.final_state == "APPLICABLE"
    assert r.missing_fact_keys == []


def test_rule_0006_v1_all_three_paths(dataset):
    r = evaluate_rule_version("RULE-0006-V1", dataset,
        {"project.dairy_liquid_milk_capacity": 25000, "project.dairy_milk_solids_capacity": 1}, NP)
    assert r.final_state == "APPLICABLE"
    r = evaluate_rule_version("RULE-0006-V1", dataset,
        {"project.dairy_liquid_milk_capacity": 100, "project.dairy_milk_solids_capacity": 0.1}, NP)
    assert r.final_state == "NOT_APPLICABLE"
    r = evaluate_rule_version("RULE-0006-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"


def test_output_mapping_is_read_from_yaml_not_hardcoded(dataset):
    # Prove the engine reads output_mapping rather than a hard-coded
    # TRUE->APPLICABLE assumption: temporarily rewrite RULE-0001-V1's
    # in-memory output_mapping and confirm the engine follows IT.
    import copy
    original = copy.deepcopy(dataset.rule_versions["RULE-0001-V1"])
    try:
        dataset.rule_versions["RULE-0001-V1"]["output_mapping"] = {
            "TRUE": "CUSTOM_TEST_STATE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION",
        }
        r = evaluate_rule_version("RULE-0001-V1", dataset,
            {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
        assert r.final_state == "CUSTOM_TEST_STATE"
    finally:
        dataset.rule_versions["RULE-0001-V1"] = original


def test_all_six_rule_versions_exist_and_have_status_draft(dataset):
    expected = {f"RULE-{i:04d}-V1" for i in range(1, 7)}
    assert expected == set(dataset.rule_versions.keys())
    for rv_id in expected:
        assert dataset.rule_versions[rv_id]["status"] == "DRAFT"


def test_rule_version_provenance_fields_populated(dataset):
    for rv_id in [f"RULE-{i:04d}-V1" for i in range(1, 7)]:
        rv = dataset.rule_versions[rv_id]
        assert rv.get("regulatory_fact_ids")
        assert rv.get("authority_id")
        assert rv.get("instrument_id")
