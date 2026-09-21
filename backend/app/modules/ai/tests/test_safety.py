"""Tests for SafetyValidator in IRIS AI Module."""

import math
import pytest

from app.modules.ai.schemas import (
    ApplicantDocumentExtraction,
    CandidateStatus,
    ConditionLogic,
    Provenance,
    QualifierType,
    RegulatoryCandidate,
    RegulatoryCondition,
    RegulatoryQualifier,
)
from app.modules.ai.validators.safety import SafetyValidator


# ==============================================================================
# TEST AI-SAFE-01: Invalid numeric values rejected (NaN, infinite, negative)
# ==============================================================================
def test_ai_safe_01_invalid_numeric_values_rejected():
    # 1. Document with negative worker count and NaN capacity
    doc = ApplicantDocumentExtraction(
        worker_count=-5,
        capacity_value=float("nan"),
    )
    res = SafetyValidator.validate_document_extraction(doc)
    assert res.valid is False
    codes = [i.code for i in res.issues]
    assert "NEGATIVE_WORKER_COUNT" in codes
    assert "INVALID_NUMERIC" in codes

    # 2. Regulatory condition with infinite threshold
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Water Consent",
        conditions=[
            RegulatoryCondition(
                fact_text="water_consumption",
                value=float("inf"),
            )
        ],
    )
    cand_res = SafetyValidator.validate_regulatory_candidate(cand)
    assert cand_res.valid is False
    assert any(i.code == "INVALID_NUMERIC" for i in cand_res.issues)


# ==============================================================================
# TEST AI-SAFE-02: Reversed ranges rejected
# ==============================================================================
def test_ai_safe_02_reversed_ranges_rejected():
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Investment Declaration",
        conditions=[
            RegulatoryCondition(
                fact_text="investment_crore_inr",
                comparison_text="between",
                lower_value=20.0,
                upper_value=5.0,  # lower > upper
                unit="crore INR",
            )
        ],
    )
    res = SafetyValidator.validate_regulatory_candidate(cand)
    assert res.valid is False
    issue = next(i for i in res.issues if i.code == "REVERSED_RANGE")
    assert "lower_value (20.0) exceeds upper_value (5.0)" in issue.message


# ==============================================================================
# TEST AI-SAFE-03: Non-rule candidate cannot have requirement text or conditions
# ==============================================================================
def test_ai_safe_03_non_rule_candidate_cannot_be_draft_ready():
    cand = RegulatoryCandidate(
        is_regulatory_requirement=False,
        requirement_text="Historical establishment",
        conditions=[
            RegulatoryCondition(fact_text="department_established", value=1995)
        ],
    )
    res = SafetyValidator.validate_regulatory_candidate(cand)
    assert res.valid is False
    codes = [i.code for i in res.issues]
    assert "NON_RULE_CANNOT_HAVE_REQUIREMENT" in codes
    assert "NON_RULE_CANNOT_HAVE_CONDITIONS" in codes


# ==============================================================================
# TEST AI-SAFE-04: Exception preservation
# ==============================================================================
def test_ai_safe_04_exception_preservation():
    source_text = "All food processing units shall obtain registration, except units operating exclusively for research."
    # Candidate without any qualifiers extracted
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Food Processing Registration",
        conditions=[],
        qualifiers=[],
        provenance=Provenance(exact_source_text=source_text),
    )
    res = SafetyValidator.validate_regulatory_candidate(cand, source_text=source_text)
    assert res.requires_human_review is True
    assert any(i.code == "LOST_EXCEPTION_CLAUSE" for i in res.issues)

    # Adding the qualifier resolves the lost exception issue
    cand.qualifiers = [
        RegulatoryQualifier(
            qualifier_type=QualifierType.EXCEPT,
            text="units operating exclusively for research",
        )
    ]
    res_fixed = SafetyValidator.validate_regulatory_candidate(cand, source_text=source_text)
    assert not any(i.code == "LOST_EXCEPTION_CLAUSE" for i in res_fixed.issues)


# ==============================================================================
# TEST AI-SAFE-05: Invalid or missing condition logic flagged
# ==============================================================================
def test_ai_safe_05_invalid_condition_logic_flagged():
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Dual Condition NOC",
        conditions=[
            RegulatoryCondition(fact_text="capacity", value=50.0),
            RegulatoryCondition(fact_text="workers", value=20.0),
        ],
        condition_logic=None,  # Multiple conditions without logic
    )
    res = SafetyValidator.validate_regulatory_candidate(cand)
    assert any(i.code == "AMBIGUOUS_CONDITION_LOGIC" for i in res.issues)

    # Adding logic resolves the issue
    cand.condition_logic = ConditionLogic.AND
    res_fixed = SafetyValidator.validate_regulatory_candidate(cand)
    assert not any(i.code == "AMBIGUOUS_CONDITION_LOGIC" for i in res_fixed.issues)


# ==============================================================================
# TEST AI-SAFE-06: Source provenance preserved and verified against source_text
# ==============================================================================
def test_ai_safe_06_source_provenance_preserved():
    source_text = "Units exceeding 50 TPD require CTE."

    # 1. Missing provenance
    cand_missing = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="CTE",
        provenance=None,
    )
    res_missing = SafetyValidator.validate_regulatory_candidate(cand_missing, source_text=source_text)
    assert res_missing.valid is False
    assert any(i.code == "MISSING_PROVENANCE_SOURCE" for i in res_missing.issues)

    # 2. Provenance mismatch
    cand_mismatch = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="CTE",
        provenance=Provenance(exact_source_text="Completely different law text about mining."),
    )
    res_mismatch = SafetyValidator.validate_regulatory_candidate(cand_mismatch, source_text=source_text)
    assert res_mismatch.valid is False
    assert any(i.code == "PROVENANCE_MISMATCH" for i in res_mismatch.issues)


# ==============================================================================
# TEST AI-SAFE-07: No ACTIVE AI candidate status exists
# ==============================================================================
def test_ai_safe_07_no_active_ai_candidate_status_exists():
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Registration",
    )
    # Status is strictly AI_CANDIDATE
    assert cand.status == CandidateStatus.AI_CANDIDATE
    assert cand.status.value != "ACTIVE"
    assert "ACTIVE" not in [s.value for s in CandidateStatus]

# ==============================================================================
# REGULATORY SAFETY HARDENING: required structure / evidence fidelity
# ==============================================================================
def test_ai_safe_regulatory_requirement_text_required():
    source = "Units exceeding 50 TPD shall obtain environmental consent."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text=None,
        conditions=[RegulatoryCondition(fact_text="capacity", comparison_text="exceeding", value=50, unit="TPD", is_numeric=True)],
        provenance=Provenance(exact_source_text=source),
    )
    res = SafetyValidator.validate_regulatory_candidate(cand, source)
    assert res.valid is False
    assert any(i.code == "MISSING_REQUIREMENT_TEXT" for i in res.issues)


def test_ai_safe_numeric_condition_requires_structured_number():
    source = "Units employing at least 20 workers shall obtain registration."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="obtain registration",
        conditions=[RegulatoryCondition(fact_text="employing at least 20 workers", is_numeric=True, raw_snippet="employing at least 20 workers")],
        provenance=Provenance(exact_source_text=source),
    )
    res = SafetyValidator.validate_regulatory_candidate(cand, source)
    codes = {i.code for i in res.issues}
    assert "NUMERIC_CONDITION_MISSING_VALUE" in codes
    assert "SOURCE_NUMERIC_VALUE_NOT_STRUCTURED" in codes
    assert res.requires_human_review is True


def test_ai_safe_rejects_empty_or_unsupported_qualifier():
    source = "Units exceeding 50 TPD shall obtain consent."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="obtain consent",
        conditions=[RegulatoryCondition(fact_text="capacity", comparison_text="exceeding", value=50, unit="TPD", is_numeric=True)],
        qualifiers=[RegulatoryQualifier(qualifier_type=QualifierType.EXCEPT, text="")],
        provenance=Provenance(exact_source_text=source),
    )
    res = SafetyValidator.validate_regulatory_candidate(cand, source)
    codes = {i.code for i in res.issues}
    assert "EMPTY_QUALIFIER" in codes
    assert "UNSUPPORTED_QUALIFIER" in codes
    assert res.valid is False


def test_ai_safe_rejects_corrupted_raw_snippet():
    source = "Every employer engaging at least 20 contract workers must register."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="register",
        conditions=[RegulatoryCondition(fact_text="contract worker count", comparison_text="at least", value=20, unit="workers", is_numeric=True, raw_snippet="engaging at least 2:00 contract workers")],
        provenance=Provenance(exact_source_text=source),
    )
    res = SafetyValidator.validate_regulatory_candidate(cand, source)
    assert any(i.code == "RAW_SNIPPET_MISMATCH" for i in res.issues)
    assert res.valid is False


def test_ai_safe_source_guard_recognizes_postfixed_or_more_thresholds():
    for source, expected, unit in [
        ("A unit employing 20 or more workers shall obtain registration.", 20.0, "workers"),
        ("Water consumption of 10,000 litres per day or more requires a statement.", 10000.0, "litres per day"),
    ]:
        obligations = SafetyValidator._source_numeric_obligations(source)
        assert any(o["value"] == expected and o["comparison"] == "or more" and o["unit"].lower() == unit for o in obligations)
