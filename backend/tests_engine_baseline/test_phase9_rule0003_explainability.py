"""
Phase 9 Section 5 — RULE-0003 must remain explainable for all four schedule
cases, and the explanation must show REQUIRES_REVIEW came from the Rule
Version's own output_mapping, never an engine hard-code. No Schedule
C/C1/X logic is added to the engine anywhere in this phase.
"""
from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION

CASES = [
    ("GENERAL_SCHEDULE", "APPLICABLE"),
    ("SCHEDULE_C", "REQUIRES_REVIEW"),
    ("SCHEDULE_C1", "REQUIRES_REVIEW"),
    ("SCHEDULE_X", "REQUIRES_REVIEW"),
]


def test_all_four_schedule_cases_reach_the_documented_state(engine):
    for schedule, expected_state in CASES:
        d = engine.evaluate_requirement(
            "P", "REQ-0003", {"project.drug_schedule_classification": schedule}, NP
        )
        assert d["final_state"] == expected_state, schedule


def test_missing_schedule_requires_information(engine):
    d = engine.evaluate_requirement("P", "REQ-0003", {}, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"
    assert d["explanation"]["missing_facts"] == ["project.drug_schedule_classification"]


def test_every_case_explanation_traces_to_the_rule_versions_own_mapping(engine, dataset):
    raw = dataset.rule_versions["RULE-0003-V1"]["output_mapping"]
    normalized = {}
    for k, v in raw.items():
        normalized["TRUE" if k is True else "FALSE" if k is False else str(k)] = v

    for schedule, expected_state in CASES:
        d = engine.evaluate_requirement(
            "P", "REQ-0003", {"project.drug_schedule_classification": schedule}, NP
        )
        assert d["explanation"]["rule_output_mapping"] == normalized
        # The condition tree shows COND-0003's NOT_IN check against the
        # authored schedule list -- the review states visibly trace to that
        # authored condition + mapping, not to a Schedule C/C1/X branch
        # anywhere in engine code.
        tree = d["explanation"]["condition_evaluation_tree"]
        assert tree["condition_id"] == "COND-0003"
        assert tree["operator"] == "NOT_IN"
        assert tree["actual_project_value"] == schedule


def test_review_states_are_labelled_review_not_false(engine):
    for schedule in ("SCHEDULE_C", "SCHEDULE_C1", "SCHEDULE_X"):
        d = engine.evaluate_requirement(
            "P", "REQ-0003", {"project.drug_schedule_classification": schedule}, NP
        )
        assert d["final_state"] == "REQUIRES_REVIEW"
        assert d["final_state"] != "FALSE"
        assert d["final_state"] != "NOT_APPLICABLE"


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
