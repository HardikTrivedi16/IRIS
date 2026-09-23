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


def test_rule_0003_v1_coarse_gate_semantics(dataset):
    # REPURPOSED 2026-09-23 (Pharma tranche, RULE-REV-0002): RULE-0003-V1
    # is now the REQ-0003 coarse gate, symmetric TRUE->APPLICABLE/
    # FALSE->NOT_APPLICABLE/UNKNOWN->REQUIRES_INFORMATION (the old
    # asymmetric FALSE->REQUIRES_REVIEW mapping was the documented
    # RULE-REV-0002 gap this tranche resolves — see RULE-0017/0018/0019
    # for where the schedule-specific answer now lives).
    gate_true = {
        "project.manufactures_drugs_for_sale_or_distribution": True,
        "project.pharma_activity_type": "FORMULATIONS",
    }
    r = evaluate_rule_version("RULE-0003-V1", dataset, gate_true, NP)
    assert r.final_state == "APPLICABLE"

    gate_false = dict(gate_true, **{"project.pharma_activity_type": "REPACKING"})
    r = evaluate_rule_version("RULE-0003-V1", dataset, gate_false, NP)
    assert r.final_state == "NOT_APPLICABLE"

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
    # project.food_subsector: DAIRY required by the FD-04 guard
    # (COND-0037, above the pre-existing COND-0007) — see
    # regulatory-data/conditions/COND-0037.yaml.
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 60000, "project.dairy_milk_solids_capacity": 100}, NP)
    assert r.final_state == "APPLICABLE"
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 100, "project.dairy_milk_solids_capacity": 100}, NP)
    assert r.final_state == "NOT_APPLICABLE"
    r = evaluate_rule_version("RULE-0005-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"
    # partial info: one criterion known TRUE means the other need not be
    # collected (per the Rule Version's own engine_note) -> still APPLICABLE
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.food_subsector": "DAIRY", "project.dairy_liquid_milk_capacity": 60000}, NP)
    assert r.final_state == "APPLICABLE"
    assert r.missing_fact_keys == []
    # a non-dairy project must never evaluate against these capacity bands,
    # even when capacity facts happen to be present (the defect FD-04 fixes)
    r = evaluate_rule_version("RULE-0005-V1", dataset,
        {"project.food_subsector": "OTHER_FOOD_PROCESSING",
         "project.dairy_liquid_milk_capacity": 60000, "project.dairy_milk_solids_capacity": 100}, NP)
    assert r.final_state == "NOT_APPLICABLE"


def test_rule_0006_v1_all_three_paths(dataset):
    # project.food_subsector: DAIRY required by the FD-04 guard
    # (COND-0038, above the pre-existing COND-0014).
    r = evaluate_rule_version("RULE-0006-V1", dataset,
        {"project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 25000, "project.dairy_milk_solids_capacity": 1}, NP)
    assert r.final_state == "APPLICABLE"
    r = evaluate_rule_version("RULE-0006-V1", dataset,
        {"project.food_subsector": "DAIRY",
         "project.dairy_liquid_milk_capacity": 100, "project.dairy_milk_solids_capacity": 0.1}, NP)
    assert r.final_state == "NOT_APPLICABLE"
    r = evaluate_rule_version("RULE-0006-V1", dataset, {}, NP)
    assert r.final_state == "REQUIRES_INFORMATION"
    r = evaluate_rule_version("RULE-0006-V1", dataset,
        {"project.food_subsector": "OTHER_FOOD_PROCESSING",
         "project.dairy_liquid_milk_capacity": 25000, "project.dairy_milk_solids_capacity": 1}, NP)
    assert r.final_state == "NOT_APPLICABLE"


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


def test_all_thirtyone_rule_versions_exist_and_none_is_active(dataset):
    # RULE-0001..0006 (Phase 5/6) + RULE-0007..0016 (Shared+Food +
    # FSSAI currentness-correction passes) + RULE-0014-V2/0015-V2 (FSSAI
    # successors) + RULE-0017..0023 (Pharma tranche) + RULE-0024..0029 (remaining-sector
    # tranche) = 31 rule versions.
    # Not all are status DRAFT any more: RULE-0014-V1/RULE-0015-V1 are
    # SUPERSEDED (FSSAI currentness correction) — the invariant this test
    # actually protects is "nothing is ACTIVE", not "everything is DRAFT".
    assert len(dataset.rule_versions) == 31
    for rv_id, rv in dataset.rule_versions.items():
        assert rv["status"] in ("DRAFT", "SUPERSEDED"), rv_id
        assert rv["status"] != "ACTIVE", rv_id


def test_rule_version_provenance_fields_populated(dataset):
    for rv_id in [f"RULE-{i:04d}-V1" for i in range(1, 16)]:
        rv = dataset.rule_versions[rv_id]
        assert rv.get("regulatory_fact_ids")
        assert rv.get("authority_id")
        assert rv.get("instrument_id")
