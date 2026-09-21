"""
Phase 8 §10 — input validation / fail-safe. Wrong types, malformed
thresholds, unsupported operators, invalid enums, missing rule version,
broken condition reference, malformed YAML, duplicate ID, broken
Requirement reference, broken conflict reference. Expected behavior:
explicit failure / UNKNOWN / review -- never a silent guess.
"""
import os
import tempfile

import pytest
import yaml

from iris_engine.conditions import evaluate_condition, ConditionEvaluationError
from iris_engine.kleene import U
from iris_engine.validate import validate_dataset


# --- wrong types / malformed thresholds / unsupported operators -----------

def test_wrong_numeric_type_fails_safe(dataset):
    r = evaluate_condition("COND-0005", dataset.conditions,
        {"project.dairy_liquid_milk_capacity": "not-a-number"})
    assert r.result is U
    assert r.error is not None


def test_wrong_type_bool_where_number_expected_fails_safe(dataset):
    # bool is technically an int subclass in Python; the engine explicitly
    # excludes bool from the numeric-threshold acceptance to avoid True/False
    # silently comparing as 1/0.
    r = evaluate_condition("COND-0005", dataset.conditions,
        {"project.dairy_liquid_milk_capacity": True})
    assert r.result is U
    assert r.error is not None


def test_malformed_threshold_comparison_value_fails_safe():
    conditions = {"C1": {"predicate_type": "THRESHOLD_COMPARISON",
                          "target_variable_key": "project.cap", "operator": ">",
                          "comparison_value": "fifty-thousand", "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.cap": 60000})
    assert r.result is U
    assert r.error is not None


def test_unsupported_operator_fails_safe():
    conditions = {"C1": {"predicate_type": "BOOLEAN_EQUALS",
                          "target_variable_key": "project.x", "operator": "REGEX_MATCH",
                          "comparison_value": True, "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.x": True})
    assert r.result is U
    assert r.error is not None
    assert "unsupported" in r.error.lower()


def test_unsupported_operator_never_silently_succeeds():
    # confirms no code path accidentally treats an unknown operator as "=="
    conditions = {"C1": {"predicate_type": "BOOLEAN_EQUALS",
                          "target_variable_key": "project.x", "operator": "FUZZY_EQUALS",
                          "comparison_value": True, "child_condition_ids": []}}
    r1 = evaluate_condition("C1", conditions, {"project.x": True})
    r2 = evaluate_condition("C1", conditions, {"project.x": False})
    # both must fail the SAME way (UNKNOWN+error), not diverge as if the
    # operator had silently been treated as equality
    assert r1.result is U and r2.result is U
    assert r1.error == r2.error


def test_invalid_enum_not_in_requires_list_type():
    conditions = {"C1": {"predicate_type": "SET_MEMBERSHIP",
                          "target_variable_key": "project.schedule", "operator": "NOT_IN",
                          "comparison_value": "not-a-list", "child_condition_ids": []}}
    r = evaluate_condition("C1", conditions, {"project.schedule": "X"})
    assert r.result is U
    assert r.error is not None


def test_unsupported_composite_operator_fails_safe():
    conditions = {
        "A": {"predicate_type": "BOOLEAN_EQUALS", "target_variable_key": "project.a",
              "operator": "==", "comparison_value": True, "child_condition_ids": []},
        "XOR": {"predicate_type": "COMPOSITE", "operator": "XOR", "child_condition_ids": ["A"]},
    }
    r = evaluate_condition("XOR", conditions, {"project.a": True})
    assert r.result is U
    assert r.error is not None


def test_composite_with_no_children_fails_safe():
    conditions = {"EMPTY": {"predicate_type": "COMPOSITE", "operator": "AND", "child_condition_ids": []}}
    r = evaluate_condition("EMPTY", conditions, {})
    assert r.result is U
    assert r.error is not None


# --- broken references (via validate_dataset, on a synthetic mini dataset) -

@pytest.fixture()
def synthetic_regdata_dir():
    """A minimal, self-contained synthetic regulatory-data directory (NOT
    the real frozen package) used only to exercise validate_dataset's
    detection logic for duplicate IDs / broken references / malformed YAML
    without ever touching the real dataset on disk."""
    with tempfile.TemporaryDirectory() as tmp:
        for sub in ("conditions", "rules", "rule-versions", "requirements", "index", "registers"):
            os.makedirs(os.path.join(tmp, sub), exist_ok=True)
        yield tmp


def _write_yaml(path, doc):
    with open(path, "w") as f:
        yaml.safe_dump(doc, f)


class _FakeDataset:
    """Duck-typed stand-in matching the attributes validate_dataset reads
    off a real RegulatoryDataset, for the registers/index bits that aren't
    file-glob-driven."""
    def __init__(self):
        self.conditions = {}
        self.rules = {}
        self.rule_versions = {}
        self.requirements = {}
        self.rule_conflict_register = {"conflicts": []}
        self.rule_review_register = {"review_items": []}
        self.dependency_review_register = {"review_items": []}
        self.dependencies_index = {"dependencies": []}
        self.conditions_index = {}
        self.rules_index = {}
        self.requirements_index = {}


def test_duplicate_condition_id_detected(synthetic_regdata_dir):
    _write_yaml(os.path.join(synthetic_regdata_dir, "conditions", "a.yaml"),
                {"condition_id": "COND-DUP", "predicate_type": "BOOLEAN_EQUALS"})
    _write_yaml(os.path.join(synthetic_regdata_dir, "conditions", "b.yaml"),
                {"condition_id": "COND-DUP", "predicate_type": "BOOLEAN_EQUALS"})
    fake_ds = _FakeDataset()
    fake_ds.conditions = {"COND-DUP": {}}  # loader would collapse the dup; validator re-scans disk
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert any("COND-DUP" in d for d in report.duplicate_ids)
    assert not report.passed


def test_broken_evaluated_by_rule_id_reference_detected(synthetic_regdata_dir):
    fake_ds = _FakeDataset()
    fake_ds.requirements = {"REQ-X": {"evaluated_by_rule_id": "RULE-DOES-NOT-EXIST"}}
    fake_ds.rules = {}  # empty -- RULE-DOES-NOT-EXIST is indeed missing
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert any("RULE-DOES-NOT-EXIST" in b for b in report.broken_references)
    assert not report.passed


def test_broken_conflict_register_reference_detected(synthetic_regdata_dir):
    fake_ds = _FakeDataset()
    fake_ds.rule_conflict_register = {"conflicts": [
        {"conflict_id": "OVERLAP-TEST", "involved_rules": ["RULE-GHOST"]}
    ]}
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert any("RULE-GHOST" in b for b in report.broken_references)
    assert not report.passed


def test_broken_dependency_edge_reference_detected(synthetic_regdata_dir):
    fake_ds = _FakeDataset()
    fake_ds.dependencies_index = {"dependencies": [
        {"from_requirement_id": "REQ-GHOST-A", "to_requirement_id": "REQ-GHOST-B"}
    ]}
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert any("REQ-GHOST-A" in b or "REQ-GHOST-B" in b for b in report.broken_references)
    assert not report.passed


def test_status_violation_detected(synthetic_regdata_dir):
    fake_ds = _FakeDataset()
    fake_ds.rule_versions = {"RULE-X-V1": {"status": "NOT_A_REAL_STATUS", "rule_id": "RULE-X"}}
    fake_ds.rules = {"RULE-X": {}}
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert any("NOT_A_REAL_STATUS" in s for s in report.status_violations)
    assert not report.passed


def test_malformed_yaml_file_detected(synthetic_regdata_dir):
    bad_path = os.path.join(synthetic_regdata_dir, "conditions", "broken.yaml")
    with open(bad_path, "w") as f:
        f.write("condition_id: COND-BROKEN\n  bad_indent: [unclosed\n")
    fake_ds = _FakeDataset()
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert report.yaml_parse_errors
    assert not report.passed


def test_index_count_mismatch_detected(synthetic_regdata_dir):
    fake_ds = _FakeDataset()
    fake_ds.conditions = {"COND-0001": {}}
    fake_ds.conditions_index = {"counts": {"total_conditions": 99}}
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert any("total_conditions" in m for m in report.index_count_mismatches)
    assert not report.passed


def test_clean_synthetic_dataset_actually_passes(synthetic_regdata_dir):
    # sanity: the validator isn't just always failing -- confirms a genuinely
    # clean, self-consistent dataset validates cleanly too.
    fake_ds = _FakeDataset()
    fake_ds.conditions = {"COND-A": {"child_condition_ids": []}}
    fake_ds.rules = {"RULE-A": {"requirement_id": "REQ-A"}}
    fake_ds.rule_versions = {"RULE-A-V1": {"rule_id": "RULE-A", "status": "DRAFT",
                                            "condition_expression_root_id": "COND-A"}}
    fake_ds.requirements = {"REQ-A": {"evaluated_by_rule_id": "RULE-A"}}
    report = validate_dataset(synthetic_regdata_dir, fake_ds)
    assert report.passed
