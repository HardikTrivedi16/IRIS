"""
Phase 9 Section 2-3 — Condition Evaluation Tree tests: TRUE / FALSE / UNKNOWN
leaves, nested composite AND/OR trees, missing facts, and errors, all
inspectable without reconstructing the evaluation manually.
"""
from iris_engine.rules import EvaluationMode
from iris_engine.condition_tree import build_condition_tree, render_condition_tree_text

NP = EvaluationMode.NON_PRODUCTION


def test_leaf_true(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP
    )
    tree = d["explanation"]["condition_evaluation_tree"]
    assert tree["condition_id"] == "COND-0001"
    assert tree["result"] == "TRUE"
    assert tree["actual_project_value"] is True
    assert tree["expected_value"] is True
    assert tree["operator"] == "=="
    assert tree["missing_fact_keys"] == []
    assert d["final_state"] == "APPLICABLE"


def test_leaf_false(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": False}, NP
    )
    tree = d["explanation"]["condition_evaluation_tree"]
    assert tree["result"] == "FALSE"
    assert tree["actual_project_value"] is False
    assert d["final_state"] == "NOT_APPLICABLE"


def test_leaf_unknown_missing_fact(engine):
    d = engine.evaluate_requirement("P", "REQ-0001", {}, NP)
    tree = d["explanation"]["condition_evaluation_tree"]
    assert tree["result"] == "UNKNOWN"
    assert tree["actual_project_value"] is None
    assert tree["missing_fact_keys"] == ["project.likely_to_discharge_sewage_or_trade_effluent"]
    assert d["final_state"] == "REQUIRES_INFORMATION"


def test_nested_composite_tree_shape_for_fssai_dependency_rule(engine, dataset):
    # RULE-0006 (State)'s root is now COND-0038 (FD-04 dairy guard, this
    # pass): AND(food_subsector==DAIRY leaf, COND-0014 = OR(AND(COND-0008,
    # COND-0009), AND(COND-0011,COND-0012))). COND-0014 itself is
    # unchanged; only the root above it changed from COND-0014 to COND-0038.
    facts = {"project.industry": "FOOD", "project.food_subsector": "DAIRY",
             "project.dairy_liquid_milk_capacity": 40000,
             "project.dairy_milk_solids_capacity": 1000}
    d = engine.evaluate_requirement("P", "REQ-0004", facts, NP)
    tree = d["explanation"]["classification_condition_trees"]["RULE-0006"]
    assert tree["predicate_type"] == "COMPOSITE"
    assert tree["operator"] == "AND"
    assert len(tree["children"]) == 2
    guard, or_node = tree["children"]
    assert guard["predicate_type"] != "COMPOSITE"
    assert "condition_id" in guard and "result" in guard

    assert or_node["predicate_type"] == "COMPOSITE"
    assert or_node["operator"] == "OR"
    assert len(or_node["children"]) == 2
    for child in or_node["children"]:
        assert child["predicate_type"] == "COMPOSITE"
        assert child["operator"] == "AND"
        assert len(child["children"]) == 2
        for leaf in child["children"]:
            assert leaf["predicate_type"] != "COMPOSITE"
            assert "condition_id" in leaf and "result" in leaf


def test_tree_never_leaks_source_file_paths(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0003", {"project.drug_schedule_classification": "SCHEDULE_C"}, NP
    )
    import json
    blob = json.dumps(d["explanation"]["condition_evaluation_tree"])
    assert "_source_file" not in blob


def test_text_renderer_does_not_crash_on_none_tree():
    text = render_condition_tree_text(None)
    assert "no condition tree" in text


def test_text_renderer_produces_readable_ascii(engine, dataset):
    # COND-0003 is now the REQ-0003 coarse gate (manufactures_drugs +
    # activity NOT_IN [REPACKING]) — supply REPACKING so the gate itself
    # resolves FALSE, independent of drug_schedule_classification.
    facts = {
        "project.manufactures_drugs_for_sale_or_distribution": True,
        "project.pharma_activity_type": "REPACKING",
    }
    d = engine.evaluate_requirement("P", "REQ-0003", facts, NP)
    tree = d["explanation"]["condition_evaluation_tree"]
    text = render_condition_tree_text(tree)
    # The composite root's own condition_id (COND-0003) is not printed by
    # the text renderer (only leaf condition_ids and the AND/OR operator
    # are) -- confirmed by inspection, not assumed. COND-0047 is the leaf
    # that actually resolves FALSE (pharma_activity_type == REPACKING).
    assert "COND-0047" in text
    assert "FALSE" in text


def test_build_condition_tree_returns_none_for_none_input(dataset):
    assert build_condition_tree(None, dataset.conditions, {}) is None
