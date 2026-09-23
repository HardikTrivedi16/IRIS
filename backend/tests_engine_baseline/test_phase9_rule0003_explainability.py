"""
Phase 9 Section 5 — REQ-0003 must remain explainable for all four ENUM
schedule cases, and the explanation must show each result came from the
Rule Versions' own output_mapping/classification, never an engine
hard-code. No Schedule C/C1/X logic is added to the engine anywhere in
this phase.

REWRITTEN 2026-09-23 for the Pharma tranche's ENUM reshape and REQ-0003
coarse-gate + classification_rule_ids restructuring (see
regulatory-data/registers/rule_review_register.yaml RULE-REV-0002).
"""
from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION

_GATE = {
    "project.manufactures_drugs_for_sale_or_distribution": True,
    "project.pharma_activity_type": "FORMULATIONS",
}

CASES = [
    ("NONE", "APPLICABLE", "RULE-0017"),
    ("SCHEDULE_C_OR_C1", "APPLICABLE", "RULE-0018"),
    ("SCHEDULE_X_ONLY", "APPLICABLE", "RULE-0019"),
    ("SCHEDULE_C_OR_C1_AND_X", "APPLICABLE", "RULE-0019"),
]


def _facts(schedule):
    f = dict(_GATE)
    f["project.drug_schedule_classification"] = schedule
    return f


def test_all_four_schedule_cases_reach_the_documented_state(engine):
    for schedule, expected_state, firing_rule in CASES:
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        assert d["final_state"] == expected_state, schedule
        assert d["classification"]["rule_results"][firing_rule] == "APPLICABLE", schedule


def test_missing_schedule_requires_information(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", dict(_GATE), NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert d["explanation"]["missing_facts"] == ["project.drug_schedule_classification"]


def test_every_case_explanation_traces_to_the_gate_rule_versions_own_mapping(engine, dataset):
    raw = dataset.rule_versions["RULE-0003-V1"]["output_mapping"]
    normalized = {}
    for k, v in raw.items():
        normalized["TRUE" if k is True else "FALSE" if k is False else str(k)] = v

    for schedule, _, _ in CASES:
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        assert d["explanation"]["rule_output_mapping"] == normalized
        # The top-level condition tree is COND-0003 (the coarse gate,
        # now a COMPOSITE AND of the two gate leaves) -- the
        # schedule-specific answer lives in the classification block's own
        # per-rule condition trees, not in this top-level tree.
        tree = d["explanation"]["condition_evaluation_tree"]
        assert tree["condition_id"] == "COND-0003"
        assert tree["operator"] == "AND"
        assert len(tree["children"]) == 2


def test_classification_states_are_labelled_applicable_not_false(engine):
    for schedule, _, firing_rule in CASES:
        d = engine.evaluate_requirement("P", "REQ-0003", _facts(schedule), NP)
        assert d["classification"]["rule_results"][firing_rule] == "APPLICABLE"
        assert d["classification"]["rule_results"][firing_rule] != "FALSE"
        assert d["classification"]["rule_results"][firing_rule] != "NOT_APPLICABLE"


def test_no_schedule_specific_strings_appear_in_engine_source():
    import os
    engine_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "iris_engine")
    forbidden = ("SCHEDULE_C1", "SCHEDULE_X", "GENERAL_SCHEDULE")
    for fn in os.listdir(engine_dir):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(engine_dir, fn), encoding="utf-8") as f:
            content = f.read()
        for token in forbidden:
            assert token not in content, f"{token} found hard-coded in {fn}"
