"""
Phase 8 §7 — FSSAI overlap critical regression, extended beyond Phase 7's
test_fssai_overlap.py: boundary-adjacent values around the overlap, and a
synthetic unregistered-conflict scenario proving the engine fails safe with
UNREGISTERED_OVERLAP (rather than inventing a precedence) when two rules
resolve APPLICABLE simultaneously with NO matching conflict-register entry.
"""
import copy

from iris_engine.rules import EvaluationMode
from iris_engine.classification import evaluate_classification_group

NP = EvaluationMode.NON_PRODUCTION


def _facts(liquid=None, solids=None):
    # project.food_subsector: DAIRY — required by the FD-04 guard (see
    # test_fssai_overlap.py's _facts for the same fix).
    facts = {"project.industry": "FOOD", "project.food_subsector": "DAIRY"}
    if liquid is not None:
        facts["project.dairy_liquid_milk_capacity"] = liquid
    if solids is not None:
        facts["project.dairy_milk_solids_capacity"] = solids
    return facts


# --- the five exact required cases (re-verified independently here) -------

def test_case1_60000_1000(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(60000, 1000), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["classification"]["combined_state"] == "REQUIRES_REVIEW"
    assert d["classification"]["conflict_id"] == "OVERLAP-0001"
    assert d["final_state"] == "REQUIRES_REVIEW"


def test_case2_40000_3000(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(40000, 3000), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["classification"]["combined_state"] == "REQUIRES_REVIEW"
    assert d["classification"]["conflict_id"] == "OVERLAP-0001"
    assert d["final_state"] == "REQUIRES_REVIEW"


def test_case3_40000_1000(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(40000, 1000), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["final_state"] == "APPLICABLE"


def test_case4_50000_2500(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(50000, 2500), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["final_state"] == "APPLICABLE"


def test_case5_missing_both(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(None, None), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "REQUIRES_INFORMATION"
    assert d["classification"]["rule_results"]["RULE-0006"] == "REQUIRES_INFORMATION"
    assert d["final_state"] == "REQUIRES_INFORMATION"


# --- no hidden tiebreakers / precedence / conversion -----------------------

def test_no_central_or_state_precedence_wording_anywhere(engine):
    forbidden = ["central takes precedence", "state takes precedence",
                 "central prevails", "state prevails", "supersedes the",
                 "overrides the"]
    for liquid, solids in [(60000, 1000), (40000, 3000)]:
        d = engine.evaluate_requirement("P", "REQ-0004", _facts(liquid, solids), NP)
        text = d["reason_text"].lower()
        for phrase in forbidden:
            assert phrase not in text


def test_no_threshold_conversion_applied(engine):
    # 50000 L/day exactly, solids pinned to a definite non-triggering value
    # so both rules fully resolve (Kleene, not left UNKNOWN): Central's ">"
    # excludes 50000 on the liquid dimension, State's "<=" includes it.
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(50000, 0), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"


# --- boundary-adjacent values around the overlap zone ----------------------
# Each of these pins the OTHER dimension to a definite non-triggering value
# (0) so that Kleene OR/AND fully resolves rather than degrading to
# REQUIRES_INFORMATION for a genuinely-missing second dimension (F|U=U is
# correct Kleene behavior, verified separately in test_phase8_all_conditions.py
# -- these tests isolate the boundary itself, not the missing-data behavior).

def test_boundary_just_above_central_liquid_threshold_and_within_state(engine):
    # 50001 crosses Central (>50000) while still outside State's <=50000 range
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(50001, 0), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "NOT_APPLICABLE"
    assert d["final_state"] == "APPLICABLE"


def test_boundary_just_below_state_liquid_floor(engine):
    # 500 is below State's >=501 floor and below Central's >50000 -- neither applies
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(500, 0), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "NOT_APPLICABLE"
    # NOTE: per RULE-0006's scope_note / RULE-REV-0003, a FALSE/FALSE result
    # here does NOT mean "no FSSAI obligation" -- that registration-tier gap
    # is deliberately unresolved (evidence gap), not silently concluded.
    assert d["classification"]["combined_state"] == "NOT_APPLICABLE"


def test_boundary_exactly_at_state_liquid_floor_501(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(501, 0), NP)
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"


def test_boundary_exactly_at_central_solids_threshold_2500(engine):
    # 2500 exactly: Central's ">2500" excludes it; State's "<=2500" includes it
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(0, 2500), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"


def test_boundary_just_above_central_solids_2501(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(0, 2501), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "NOT_APPLICABLE"


def test_boundary_just_below_state_solids_floor(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(0, 2.4), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "NOT_APPLICABLE"


def test_boundary_exactly_at_state_solids_floor_2_5(engine):
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(0, 2.5), NP)
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"


def test_missing_one_dimension_correctly_stays_unresolved_not_false(engine):
    # Genuine Kleene behavior check distinct from the pinned-boundary tests
    # above: a FALSE known dimension plus a genuinely UNKNOWN dimension must
    # resolve UNKNOWN (F|U=U), never silently collapse to NOT_APPLICABLE.
    d = engine.evaluate_requirement("P", "REQ-0004", _facts(500, None), NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "REQUIRES_INFORMATION"
    assert d["classification"]["rule_results"]["RULE-0006"] != "NOT_APPLICABLE"


# --- synthetic unregistered-overlap: engine fails safe, invents nothing ---

def test_unregistered_simultaneous_true_fails_safe(dataset):
    """Synthetic test-only fixture: two rules attached to a fabricated
    requirement both resolve APPLICABLE with NO matching entry in the real
    rule_conflict_register.yaml. The engine must report REQUIRES_REVIEW /
    UNREGISTERED_OVERLAP rather than inventing a precedence. The dataset's
    real requirements/rules/registers are restored unconditionally via a
    deep-copied snapshot -- nothing here is persisted."""
    snapshot_requirements = copy.deepcopy(dataset.requirements)
    snapshot_rules = copy.deepcopy(dataset.rules)
    snapshot_rule_versions = copy.deepcopy(dataset.rule_versions)
    snapshot_conditions = copy.deepcopy(dataset.conditions)
    try:
        # two trivial always-TRUE leaf conditions with no registered conflict
        dataset.conditions["TEST-COND-A"] = {
            "predicate_type": "BOOLEAN_EQUALS",
            "target_variable_key": "project.test_flag_a",
            "operator": "==", "comparison_value": True, "child_condition_ids": [],
        }
        dataset.conditions["TEST-COND-B"] = {
            "predicate_type": "BOOLEAN_EQUALS",
            "target_variable_key": "project.test_flag_b",
            "operator": "==", "comparison_value": True, "child_condition_ids": [],
        }
        dataset.rule_versions["TEST-RULE-A-V1"] = {
            "rule_version_id": "TEST-RULE-A-V1", "rule_id": "TEST-RULE-A",
            "status": "DRAFT",
            "condition_expression_root_id": "TEST-COND-A",
            "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        }
        dataset.rule_versions["TEST-RULE-B-V1"] = {
            "rule_version_id": "TEST-RULE-B-V1", "rule_id": "TEST-RULE-B",
            "status": "DRAFT",
            "condition_expression_root_id": "TEST-COND-B",
            "output_mapping": {"TRUE": "APPLICABLE", "FALSE": "NOT_APPLICABLE", "UNKNOWN": "REQUIRES_INFORMATION"},
        }
        dataset.rules_index.setdefault("rules", [])
        dataset.rules_index["rules"].append(
            {"rule_id": "TEST-RULE-A", "latest_rule_version_id": "TEST-RULE-A-V1"})
        dataset.rules_index["rules"].append(
            {"rule_id": "TEST-RULE-B", "latest_rule_version_id": "TEST-RULE-B-V1"})
        dataset.requirements["TEST-REQ-SYNTH"] = {
            "requirement_id": "TEST-REQ-SYNTH",
            "evaluated_by_rule_id": None,
            "classification_rule_ids": ["TEST-RULE-A", "TEST-RULE-B"],
        }

        result = evaluate_classification_group(
            "TEST-REQ-SYNTH", dataset,
            {"project.test_flag_a": True, "project.test_flag_b": True},
            evaluation_mode=NP,
        )
        assert result.rule_evaluations["TEST-RULE-A"].final_state == "APPLICABLE"
        assert result.rule_evaluations["TEST-RULE-B"].final_state == "APPLICABLE"
        assert result.combined_state == "REQUIRES_REVIEW"
        assert result.review_reason == "UNREGISTERED_OVERLAP"
        # critically: no conflict_id is fabricated
        assert result.conflict_id is None
    finally:
        dataset.requirements = snapshot_requirements
        dataset.rules = snapshot_rules
        dataset.rule_versions = snapshot_rule_versions
        dataset.conditions = snapshot_conditions
        # rules_index was mutated in place; reload it fresh from disk to
        # guarantee full restoration regardless of the mutation above.
        import os
        from iris_engine.loader import _load_yaml_file
        dataset.rules_index = _load_yaml_file(
            os.path.join(dataset.root, "index", "rules_index.yaml")) or {}


def test_regulatory_data_untouched_by_synthetic_overlap_test(dataset):
    # sanity: the real REQ-0004 / RULE-0005 / RULE-0006 are unaffected by
    # the synthetic fixture in the previous test (order-independent check).
    assert "TEST-REQ-SYNTH" not in dataset.requirements
    assert "TEST-RULE-A-V1" not in dataset.rule_versions
    assert dataset.requirements["REQ-0004"]["classification_rule_ids"] == ["RULE-0005", "RULE-0006"]
