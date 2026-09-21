from iris_engine.conditions import evaluate_condition
from iris_engine.kleene import T, F, U


def test_leaf_boolean_equals_true():
    conditions = {"C1": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.x",
                          "operator": "==", "comparison_value": True, "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.x": True})
    assert r.result is T


def test_leaf_boolean_equals_false():
    conditions = {"C1": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.x",
                          "operator": "==", "comparison_value": True, "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.x": False})
    assert r.result is F


def test_leaf_missing_fact_is_unknown_not_false():
    conditions = {"C1": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.x",
                          "operator": "==", "comparison_value": True, "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {})
    assert r.result is U
    assert r.missing_fact_keys == ["project.x"]


def test_leaf_threshold_greater_than():
    conditions = {"C1": {"predicate_type": "THRESHOLD_COMPARISON", "target_variable_key": "project.cap",
                          "operator": ">", "comparison_value": 50000, "child_condition_ids": []}}
    assert evaluate_condition("C1", conditions, {"project.cap": 60000}).result is T
    assert evaluate_condition("C1", conditions, {"project.cap": 50000}).result is F
    assert evaluate_condition("C1", conditions, {"project.cap": 1}).result is F


def test_leaf_not_in():
    conditions = {"C1": {"predicate_type": "SET_MEMBERSHIP", "target_variable_key": "project.schedule",
                          "operator": "NOT_IN", "comparison_value": ["A", "B"], "child_condition_ids": []}}
    assert evaluate_condition("C1", conditions, {"project.schedule": "C"}).result is T
    assert evaluate_condition("C1", conditions, {"project.schedule": "A"}).result is F


def test_leaf_invalid_input_fails_safe_to_unknown():
    # threshold operator applied to a non-numeric fact value
    conditions = {"C1": {"predicate_type": "THRESHOLD_COMPARISON", "target_variable_key": "project.cap",
                          "operator": ">", "comparison_value": 50000, "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.cap": "not-a-number"})
    assert r.result is U
    assert r.error is not None


def test_leaf_unsupported_operator_fails_safe():
    conditions = {"C1": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.x",
                          "operator": "!=", "comparison_value": True, "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.x": True})
    assert r.result is U
    assert r.error is not None


def test_composite_and_or():
    conditions = {
        "A": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.a",
              "operator": "==", "comparison_value": True, "child_condition_ids": []},
        "B": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.b",
              "operator": "==", "comparison_value": True, "child_condition_ids": []},
        "AND": {"predicate_type": "COMPOSITE", "operator": "AND", "child_condition_ids": ["A", "B"]},
        "OR": {"predicate_type": "COMPOSITE", "operator": "OR", "child_condition_ids": ["A", "B"]},
    }
    assert evaluate_condition("AND", conditions, {"project.a": True, "project.b": True}).result is T
    assert evaluate_condition("AND", conditions, {"project.a": True, "project.b": False}).result is F
    assert evaluate_condition("OR", conditions, {"project.a": True, "project.b": False}).result is T
    assert evaluate_condition("OR", conditions, {"project.a": False}).result is U  # b missing => F|U=U


def test_missing_condition_id_fails_safe():
    r = evaluate_condition("DOES-NOT-EXIST", {}, {})
    assert r.result is U
    assert r.error is not None
