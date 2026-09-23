from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION


def test_rule_0001_water_act(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    assert d["final_state"] == "APPLICABLE"

    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": False}, NP)
    assert d["final_state"] == "NOT_APPLICABLE"

    d = engine.evaluate_requirement("P", "REQ-0001", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


def test_rule_0002_air_act(engine):
    d = engine.evaluate_requirement("P", "REQ-0002",
        {"project.plant_located_in_air_pollution_control_area": True}, NP)
    assert d["final_state"] == "APPLICABLE"

    d = engine.evaluate_requirement("P", "REQ-0002",
        {"project.plant_located_in_air_pollution_control_area": False}, NP)
    assert d["final_state"] == "NOT_APPLICABLE"

    d = engine.evaluate_requirement("P", "REQ-0002", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


_PHARMA_GATE = {
    "project.manufactures_drugs_for_sale_or_distribution": True,
    "project.pharma_activity_type": "FORMULATIONS",
}


def test_rule_0003_drugs_schedule_none(engine):
    facts = dict(_PHARMA_GATE, **{"project.drug_schedule_classification": "NONE"})
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    assert d["final_state"] == "APPLICABLE"


def test_rule_0003_schedule_c_or_c1_applicable_not_not_applicable(engine):
    facts = dict(_PHARMA_GATE, **{"project.drug_schedule_classification": "SCHEDULE_C_OR_C1"})
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    assert d["final_state"] == "APPLICABLE"
    assert d["final_state"] != "NOT_APPLICABLE"


def test_rule_0003_schedule_x_only_applicable(engine):
    facts = dict(_PHARMA_GATE, **{"project.drug_schedule_classification": "SCHEDULE_X_ONLY"})
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    assert d["final_state"] == "APPLICABLE"


def test_rule_0003_schedule_c_or_c1_and_x_applicable(engine):
    facts = dict(_PHARMA_GATE, **{"project.drug_schedule_classification": "SCHEDULE_C_OR_C1_AND_X"})
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    assert d["final_state"] == "APPLICABLE"


def test_rule_0003_missing_schedule_requires_information(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


def test_rule_0004_fssai_food_business(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", {"project.industry": "FOOD"}, NP)
    assert d["final_state"] in ("APPLICABLE", "REQUIRES_INFORMATION")  # classification may add REQUIRES_INFORMATION
    d = engine.evaluate_requirement("P", "REQ-0004", {"project.industry": "PHARMA"}, NP)
    assert d["final_state"] == "NOT_APPLICABLE"
    d = engine.evaluate_requirement("P", "REQ-0004", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


def test_rule_0005_and_0006_direct(engine, dataset):
    from iris_engine.rules import evaluate_rule_version
    dairy_facts = {"project.food_subsector": "DAIRY",
                   "project.dairy_liquid_milk_capacity": 60000,
                   "project.dairy_milk_solids_capacity": 1000}
    rv5 = evaluate_rule_version("RULE-0005-V1", dataset, dairy_facts, NP)
    assert rv5.final_state == "APPLICABLE"

    rv6 = evaluate_rule_version("RULE-0006-V1", dataset, dairy_facts, NP)
    assert rv6.final_state == "APPLICABLE"
