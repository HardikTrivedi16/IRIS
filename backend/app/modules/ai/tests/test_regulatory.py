"""Tests for RegulatoryAIService in IRIS AI Module."""

from typing import Any
import pytest

from app.modules.ai import (
    CandidateStatus,
    ConditionLogic,
    Provenance,
    QualifierType,
    RegulatoryCandidate,
    RegulatoryCandidateResult,
    RegulatoryCondition,
    RegulatoryQualifier,
    VerificationIssue,
    VerificationMode,
    VerificationResult,
    VerificationVerdict,
    _reset_ai_facade,
)
from app.modules.ai.exceptions import AIVerificationError
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.regulatory import RegulatoryAIService
from app.modules.ai.services.verification import VerificationService


class MockRegAIProvider(BaseAIProvider):
    """Mock Core AI Provider returning predetermined RegulatoryCandidate objects."""

    def __init__(self, candidate_return: Any = None) -> None:
        self.candidate_return = candidate_return
        self.last_prompt = ""

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return "mock text"

    def generate_structured(self, prompt: str, schema: type[Any], **kwargs: Any) -> Any:
        self.last_prompt = prompt
        return self.candidate_return

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def health_check(self) -> bool:
        return True


class MockRegVerifier(BaseVerificationProvider):
    """Mock Verification Provider for RegulatoryAIService."""

    def __init__(self, result: VerificationResult | None = None, exc: Exception | None = None) -> None:
        self.result = result or VerificationResult(
            verdict=VerificationVerdict.PASS,
            issues=[],
            corrected_output=None,
            verifier_provider="mock_verifier",
        )
        self.exc = exc

    def verify(self, task_type: str, authoritative_input: Any, local_output: Any, **kwargs: Any) -> VerificationResult:
        if self.exc:
            raise self.exc
        return self.result


@pytest.fixture(autouse=True)
def clean_state():
    _reset_ai_facade()
    yield
    _reset_ai_facade()


# ==============================================================================
# TEST AI-REG-01: greater than 50 TPD
# ==============================================================================
def test_ai_reg_01_greater_than_50_tpd():
    source_text = "A food processing unit with production capacity greater than 50 TPD shall obtain environmental consent before commercial operation."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="environmental consent",
        conditions=[
            RegulatoryCondition(
                fact_text="production capacity",
                comparison_text="greater than",
                value=50.0,
                unit="TPD",
                is_numeric=True,
            )
        ],
        timing_text="before commercial operation",
        provenance=Provenance(exact_source_text=source_text),
    )
    provider = MockRegAIProvider(candidate_return=cand)
    core = CoreAIService(provider=provider)
    verification = VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF)
    service = RegulatoryAIService(core=core, verification=verification)

    res = service.extract_candidate(source_text)
    assert res.candidate.is_regulatory_requirement is True
    assert res.candidate.conditions[0].comparison_text == "greater than"
    assert res.candidate.conditions[0].value == 50.0
    assert res.candidate.conditions[0].unit == "TPD"
    assert res.candidate.timing_text == "before commercial operation"
    assert res.safety_valid is True


# ==============================================================================
# TEST AI-REG-02: at least 25 workers
# ==============================================================================
def test_ai_reg_02_at_least_25_workers():
    source_text = "An industrial unit employing at least 25 workers shall obtain labour registration."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="labour registration",
        conditions=[
            RegulatoryCondition(
                fact_text="worker count",
                comparison_text="at least",
                value=25.0,
                unit="workers",
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.candidate.conditions[0].comparison_text == "at least"
    assert res.candidate.conditions[0].value == 25.0


# ==============================================================================
# TEST AI-REG-03: not exceeding 5000 litres per day
# ==============================================================================
def test_ai_reg_03_not_exceeding_5000_litres():
    source_text = "Water consumption not exceeding 5000 litres per day shall require a simplified water-use statement."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="simplified water-use statement",
        conditions=[
            RegulatoryCondition(
                fact_text="water consumption",
                comparison_text="not exceeding",
                value=5000.0,
                unit="litres per day",
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.candidate.conditions[0].comparison_text == "not exceeding"
    assert res.candidate.conditions[0].value == 5000.0


# ==============================================================================
# TEST AI-REG-04: between 5 and 20 crore INR
# ==============================================================================
def test_ai_reg_04_between_5_and_20_crore():
    source_text = "Project investment between 5 crore INR and 20 crore INR shall require an investment declaration."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="investment declaration",
        conditions=[
            RegulatoryCondition(
                fact_text="project investment",
                comparison_text="between",
                lower_value=5.0,
                upper_value=20.0,
                unit="crore INR",
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    cond = res.candidate.conditions[0]
    assert cond.comparison_text == "between"
    assert cond.lower_value == 5.0
    assert cond.upper_value == 20.0


# ==============================================================================
# TEST AI-REG-05: two AND conditions
# ==============================================================================
def test_ai_reg_05_two_and_conditions():
    source_text = "Production capacity greater than 50 TPD AND employing at least 20 workers."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Special Consent",
        conditions=[
            RegulatoryCondition(fact_text="capacity", comparison_text="greater than", value=50.0, unit="TPD"),
            RegulatoryCondition(fact_text="workers", comparison_text="at least", value=20.0, unit="workers"),
        ],
        condition_logic=ConditionLogic.AND,
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert len(res.candidate.conditions) == 2
    assert res.candidate.condition_logic == ConditionLogic.AND


# ==============================================================================
# TEST AI-REG-06: two OR conditions
# ==============================================================================
def test_ai_reg_06_two_or_conditions():
    source_text = "Within 2 kilometres of a notified river OR within 1 kilometre of a protected wetland."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Eco Sensitive Buffer NOC",
        conditions=[
            RegulatoryCondition(fact_text="distance to notified river", comparison_text="within", value=2.0, unit="km"),
            RegulatoryCondition(fact_text="distance to protected wetland", comparison_text="within", value=1.0, unit="km"),
        ],
        condition_logic=ConditionLogic.OR,
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert len(res.candidate.conditions) == 2
    assert res.candidate.condition_logic == ConditionLogic.OR


# ==============================================================================
# TEST AI-REG-07: non-numeric wastewater condition
# ==============================================================================
def test_ai_reg_07_non_numeric_condition():
    source_text = "A unit generating industrial wastewater shall provide a wastewater management plan."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="wastewater management plan",
        conditions=[
            RegulatoryCondition(
                fact_text="generating industrial wastewater",
                comparison_text="is true",
                value=True,
                is_numeric=False,
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    cond = res.candidate.conditions[0]
    assert cond.is_numeric is False
    assert cond.fact_text == "generating industrial wastewater"


# ==============================================================================
# TEST AI-REG-08: explicit except clause
# ==============================================================================
def test_ai_reg_08_explicit_except_clause():
    source_text = "Every food processing unit shall obtain registration, except units operating exclusively for research."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Food Registration",
        qualifiers=[
            RegulatoryQualifier(
                qualifier_type=QualifierType.EXCEPT,
                text="units operating exclusively for research",
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert len(res.candidate.qualifiers) == 1
    assert res.candidate.qualifiers[0].qualifier_type == QualifierType.EXCEPT
    assert "exclusively for research" in res.candidate.qualifiers[0].text


# ==============================================================================
# TEST AI-REG-09: unless clause
# ==============================================================================
def test_ai_reg_09_unless_clause():
    source_text = "A site plan shall be submitted unless the project is located within an approved industrial estate."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Site Plan Submission",
        qualifiers=[
            RegulatoryQualifier(
                qualifier_type=QualifierType.UNLESS,
                text="the project is located within an approved industrial estate",
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert len(res.candidate.qualifiers) == 1
    assert res.candidate.qualifiers[0].qualifier_type == QualifierType.UNLESS


# ==============================================================================
# TEST AI-REG-10: descriptive text is NOT a regulatory requirement
# ==============================================================================
def test_ai_reg_10_descriptive_text_not_requirement():
    source_text = "The Department was established to coordinate industrial services."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=False,
        requirement_text=None,
        conditions=[],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.candidate.is_regulatory_requirement is False
    assert res.requires_human_review is True  # Non-requirements require review or cannot be drafted


# ==============================================================================
# TEST AI-REG-11: hypothetical/example text is NOT a regulatory requirement
# ==============================================================================
def test_ai_reg_11_hypothetical_example_not_requirement():
    source_text = "For example, a project increasing from 40 TPD to 70 TPD would cross a hypothetical 50 TPD threshold."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=False,
        requirement_text=None,
        conditions=[],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.candidate.is_regulatory_requirement is False


# ==============================================================================
# TEST AI-REG-12: range lower > upper is rejected/marked for review
# ==============================================================================
def test_ai_reg_12_reversed_range_rejected():
    source_text = "Invalid range between 20 and 5 crore."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Invalid Range Rule",
        conditions=[
            RegulatoryCondition(
                fact_text="investment",
                lower_value=20.0,
                upper_value=5.0,
            )
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert any("REVERSED_RANGE" in w for w in res.warnings)


# ==============================================================================
# TEST AI-REG-13: exceptions are not silently lost
# ==============================================================================
def test_ai_reg_13_exceptions_not_lost():
    source_text = "Every unit must file returns, except seasonal agro-units."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Return Filing",
        qualifiers=[],  # Model omitted the exception
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.requires_human_review is True
    assert any("LOST_EXCEPTION_CLAUSE" in w for w in res.warnings)


# ==============================================================================
# TEST AI-REG-14: provenance is preserved exactly
# ==============================================================================
def test_ai_reg_14_provenance_preserved_exactly():
    source_text = "Units exceeding 50 TPD must register."
    prov = Provenance(
        source_id="SRC-ENV-2026",
        document_name="Environment_Act_Notification.pdf",
        page_number=4,
        section_reference="Section 5(b)",
        exact_source_text=source_text,
    )
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Registration",
        provenance=prov,
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text, provenance=prov)
    assert res.candidate.provenance.source_id == "SRC-ENV-2026"
    assert res.candidate.provenance.section_reference == "Section 5(b)"
    assert res.candidate.provenance.exact_source_text == source_text


# ==============================================================================
# TEST AI-REG-15: candidate can NEVER be ACTIVE
# ==============================================================================
def test_ai_reg_15_candidate_never_active():
    source_text = "Rule text"
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Sample Rule",
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.candidate.status == CandidateStatus.AI_CANDIDATE
    assert res.candidate.status.value != "ACTIVE"


# ==============================================================================
# TEST AI-REG-16: required verifier correction is revalidated against Pydantic schema
# ==============================================================================
def test_ai_reg_16_required_verifier_correction_revalidated():
    source_text = "Units between 5 and 20 crore require declaration."
    cand_local = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Declaration",
        conditions=[
            RegulatoryCondition(fact_text="investment", lower_value=5.0, upper_value=2.0)  # Typo in upper_value
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    cand_corrected = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="Declaration",
        conditions=[
            RegulatoryCondition(fact_text="investment", lower_value=5.0, upper_value=20.0)  # Corrected to 20
        ],
        provenance=Provenance(exact_source_text=source_text),
    )
    verifier = MockRegVerifier(
        result=VerificationResult(
            verdict=VerificationVerdict.CORRECTED,
            issues=[VerificationIssue(code="RANGE_CORRECTION", field="upper_value", message="Corrected 2 to 20")],
            corrected_output=cand_corrected,
            verifier_provider="mock_groq",
        )
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand_local)),
        verification=VerificationService(provider=verifier, mode=VerificationMode.REQUIRED),
    )
    res = service.extract_candidate(source_text)
    assert res.candidate.conditions[0].upper_value == 20.0
    assert res.outcome.corrected_by_verifier is True


# ==============================================================================
# TEST AI-REG-17: verification failure does not silently produce a trusted candidate
# ==============================================================================
def test_ai_reg_17_verification_failure_not_trusted():
    source_text = "Some regulatory text."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="NOC",
        provenance=Provenance(exact_source_text=source_text),
    )
    # Verifier raises AIVerificationError in REQUIRED mode
    verifier = MockRegVerifier(exc=AIVerificationError("Verifier rejected output in REQUIRED mode"))
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=verifier, mode=VerificationMode.REQUIRED),
    )
    res = service.extract_candidate(source_text)
    # The candidate must NOT be trusted
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert any("Verification failed in REQUIRED mode" in w for w in res.warnings)


# ==============================================================================
# TEST AI-REG-18: regulatory service never evaluates project applicability
# ==============================================================================
def test_ai_reg_18_no_project_applicability_evaluation():
    from app.modules.ai.services import regulatory
    import inspect

    source_code = inspect.getsource(regulatory)
    assert "RuleEngine" not in source_code
    assert "project_facts" not in source_code
    assert "app.modules.rules" not in source_code
    assert not hasattr(RegulatoryAIService, "evaluate")
    assert not hasattr(RegulatoryAIService, "evaluate_applicability")
    assert not hasattr(RegulatoryAIService, "check_applicability")


# ==============================================================================
# OPTIONAL LIVE PHASE 3 SMOKE TEST
# Skipped by default. Run manually with:
# pytest app/modules/ai/tests/test_regulatory.py -v -m "live_phase3"
# ==============================================================================
@pytest.mark.live_phase3
def test_live_phase3_regulatory_candidate_smoke():
    from app.modules.ai import get_ai
    ai = get_ai()
    if not ai.core.health():
        pytest.skip("Local Ollama daemon is not reachable at configured URL")

    synthetic_rule_text = (
        "A food processing unit with production capacity greater than 50 TPD and "
        "employing at least 20 workers shall submit an occupational and environmental safety plan "
        "before commercial operation."
    )
    res = ai.regulatory.extract_candidate(synthetic_rule_text)
    assert res.candidate.is_regulatory_requirement is True
    # Confirm output remains AI_CANDIDATE and NEVER ACTIVE
    assert res.candidate.status == CandidateStatus.AI_CANDIDATE
    assert res.candidate.status.value != "ACTIVE"


# ==============================================================================
# REGULATORY SAFETY HARDENING REGRESSION TESTS
# ==============================================================================
def test_ai_reg_safety_flags_source_numeric_threshold_left_only_in_prose():
    source_text = "Industrial occupancies accommodating at least 50 workers on a single shift must provide dual separate fire exit staircases."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="provide dual separate fire exit staircases",
        conditions=[RegulatoryCondition(
            fact_text="accommodating at least 50 workers on a single shift",
            comparison_text=None,
            value=None,
            unit=None,
            is_numeric=False,
            raw_snippet="accommodating at least 50 workers on a single shift",
        )],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert any("SOURCE_NUMERIC_VALUE_NOT_STRUCTURED" in w for w in res.warnings)


def test_ai_reg_safety_flags_source_range_left_only_in_prose():
    source_text = "Facilities operating with boiler pressure between 5.0 and 20.0 kg/cm2 shall undergo annual testing."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="annual testing",
        conditions=[RegulatoryCondition(
            fact_text="boiler pressure between 5.0 and 20.0 kg/cm2",
            comparison_text=None,
            lower_value=None,
            upper_value=None,
            unit=None,
            is_numeric=True,
        )],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert sum("SOURCE_NUMERIC_VALUE_NOT_STRUCTURED" in w for w in res.warnings) >= 2


def test_ai_reg_safety_flags_lost_qualitative_scope_predicate():
    source_text = "All agro-processing factories shall maintain automatic fire sprinkler networks across storage godowns."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="maintain automatic fire sprinkler networks",
        conditions=[RegulatoryCondition(
            fact_text="maintain automatic fire sprinkler networks",
            is_numeric=False,
        )],
        provenance=Provenance(exact_source_text=source_text),
    )
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=MockRegVerifier(), mode=VerificationMode.OFF),
    )
    res = service.extract_candidate(source_text)
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert any("SOURCE_QUALITATIVE_PREDICATE_NOT_STRUCTURED" in w for w in res.warnings)


def test_ai_reg_invalid_required_verifier_correction_degrades_to_review():
    from app.modules.ai.exceptions import AIInvalidOutputError

    source_text = "Units at least 20 workers must register."
    cand = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="register",
        conditions=[RegulatoryCondition(fact_text="workers", comparison_text="at least", value=20, unit="workers")],
        provenance=Provenance(exact_source_text=source_text),
    )
    # A verifier CORRECTED payload that cannot validate against RegulatoryCandidate.
    verifier = MockRegVerifier(result=VerificationResult(
        verdict=VerificationVerdict.CORRECTED,
        issues=[VerificationIssue(code="TEST_CORRECTION", field="qualifiers", message="Synthetic invalid correction for degradation test.")],
        corrected_output={"is_regulatory_requirement": True, "qualifiers": [{"qualifier_type": "BY", "text": "x"}]},
        verifier_provider="mock_groq",
    ))
    service = RegulatoryAIService(
        core=CoreAIService(provider=MockRegAIProvider(cand)),
        verification=VerificationService(provider=verifier, mode=VerificationMode.REQUIRED),
    )
    res = service.extract_candidate(source_text)
    assert res.requires_human_review is True
    assert res.safety_valid is False
    assert any("Verification failed in REQUIRED mode" in w for w in res.warnings)


def test_ai_facade_noop_verifier_cannot_masquerade_as_required_verification():
    from app.modules.ai.config import AIConfig
    from app.modules.ai.facade import IRISAI
    from app.modules.ai.providers.noop_verifier import NoOpVerifier

    config = AIConfig(verifier_enabled=True, verifier_provider="noop")
    ai = IRISAI(config=config, verification_provider=NoOpVerifier())
    assert ai.verification.mode == VerificationMode.OFF
    assert ai.regulatory_verification.mode == VerificationMode.OFF
