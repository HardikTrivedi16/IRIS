"""Contract-driven regression tests added by the exhaustive core-AI audit."""
from typing import Any
import pytest
from pydantic import ValidationError

from app.modules.ai import (
    AIConfig, ApplicantDocumentExtraction, DependencyExplanation, DependencyInput,
    GroundedAnswer, Provenance, RegulatoryCandidate, RegulatoryCondition,
    RegulatorySourceChunk, RetrievalResult, VerificationMode,
)
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.noop_verifier import NoOpVerifier
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.documents import DocumentAIService
from app.modules.ai.services.explanations import ExplanationService
from app.modules.ai.services.regulatory import RegulatoryAIService
from app.modules.ai.services.retrieval import RetrievalService
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator


class StaticProvider(BaseAIProvider):
    def __init__(self, value: Any): self.value = value
    def generate(self, prompt: str, **kwargs: Any) -> str: return str(self.value)
    def generate_structured(self, prompt: str, schema: type[Any], **kwargs: Any) -> Any: return self.value
    def embed(self, texts: list[str]) -> list[list[float]]: return [[1.0, 0.0] for _ in texts]
    def health_check(self) -> bool: return True


def off_verification() -> VerificationService:
    return VerificationService(NoOpVerifier(), VerificationMode.OFF)


def test_document_missing_confidence_requires_human_confirmation():
    extraction = ApplicantDocumentExtraction(business_name="ABC Foods")
    result = SafetyValidator.validate_document_extraction(extraction, source_text="ABC Foods")
    assert result.valid is True
    assert result.requires_human_review is True
    assert any(i.code == "MISSING_FIELD_CONFIDENCE" for i in result.issues)


def test_document_low_confidence_requires_human_confirmation():
    extraction = ApplicantDocumentExtraction(business_name="ABC Foods", field_confidence={"business_name": 0.4})
    result = SafetyValidator.validate_document_extraction(extraction, source_text="ABC Foods", low_confidence_threshold=0.75)
    assert result.requires_human_review is True
    assert any(i.code == "LOW_CONFIDENCE_EXTRACTION" for i in result.issues)


def test_document_caller_provenance_overrides_model_provenance():
    extraction = ApplicantDocumentExtraction(
        business_name="ABC Foods", field_confidence={"business_name": 0.99},
        provenance=Provenance(source_id="HALLUCINATED", exact_source_text="wrong"),
    )
    svc = DocumentAIService(CoreAIService(StaticProvider(extraction)), off_verification())
    authoritative = Provenance(source_id="DOC-1", page_number=1)
    result = svc.extract("ABC Foods", provenance=authoritative)
    assert result.data.provenance is not None
    assert result.data.provenance.source_id == "DOC-1"
    assert result.data.provenance.exact_source_text == "ABC Foods"


def test_regulatory_candidate_always_requires_authorised_human_review():
    candidate = RegulatoryCandidate(
        is_regulatory_requirement=True,
        requirement_text="obtain registration",
        conditions=[],
        provenance=Provenance(exact_source_text="Every unit shall obtain registration."),
    )
    svc = RegulatoryAIService(CoreAIService(StaticProvider(candidate)), off_verification())
    result = svc.extract_candidate("Every unit shall obtain registration.")
    assert result.requires_human_review is True
    assert result.candidate.requires_human_review is True


def test_regulatory_wrong_comparison_is_deterministically_rejected():
    source = "A unit employing at least 20 workers shall obtain registration."
    candidate = RegulatoryCandidate(
        is_regulatory_requirement=True, requirement_text="obtain registration",
        conditions=[RegulatoryCondition(fact_text="worker count", comparison_text="less than", value=20, unit="workers", is_numeric=True)],
        provenance=Provenance(exact_source_text=source),
    )
    result = SafetyValidator.validate_regulatory_candidate(candidate, source)
    assert result.valid is False
    assert any(i.code == "SOURCE_COMPARISON_NOT_STRUCTURED" for i in result.issues)


def test_regulatory_wrong_unit_is_deterministically_rejected():
    source = "A unit employing at least 20 workers shall obtain registration."
    candidate = RegulatoryCandidate(
        is_regulatory_requirement=True, requirement_text="obtain registration",
        conditions=[RegulatoryCondition(fact_text="worker count", comparison_text="at least", value=20, unit="TPD", is_numeric=True)],
        provenance=Provenance(exact_source_text=source),
    )
    result = SafetyValidator.validate_regulatory_candidate(candidate, source)
    assert result.valid is False
    assert any(i.code == "SOURCE_UNIT_NOT_STRUCTURED" for i in result.issues)


def test_explanation_omitted_authoritative_status_is_not_silently_accepted():
    inp = DependencyInput(requirement="CTO", status="BLOCKED", blocked_by=[])
    out = DependencyExplanation(explanation="CTO has workflow information.", requirement="CTO", status=None)
    result = SafetyValidator.validate_explanation("explanation_dependency", inp, out)
    assert result.valid is False
    assert any(i.field == "status" and i.code == "STRUCTURED_FIDELITY_MISMATCH" for i in result.issues)


def test_dependency_critical_path_flag_must_match_exactly():
    inp = DependencyInput(requirement="CTO", status="BLOCKED", blocked_by=["CTE"], requirement_on_critical_path=False)
    out = DependencyExplanation(
        explanation="CTO is blocked by CTE.", requirement="CTO", status="BLOCKED",
        blocked_by=["CTE"], requirement_on_critical_path=True,
    )
    result = SafetyValidator.validate_explanation("explanation_dependency", inp, out)
    assert result.valid is False
    assert any(i.field == "requirement_on_critical_path" for i in result.issues)


def test_rag_substantive_answer_without_citation_requires_review():
    answer = GroundedAnswer(answer="Environmental consent is required.", citations=[], insufficient_information=False)
    svc = RetrievalService(CoreAIService(StaticProvider(answer)), off_verification())
    chunk = RegulatorySourceChunk(chunk_id="C1", source_id="S1", text="Environmental consent is required.")
    result = svc.answer("What is required?", sources=[RetrievalResult(chunk=chunk, similarity_score=0.9, rank=1)])
    assert result.citations_valid is False
    assert result.requires_human_review is True
    assert any("MISSING_CITATION" in w for w in result.warnings)


def test_invalid_verifier_provider_configuration_fails_fast():
    with pytest.raises(ValidationError):
        AIConfig(verifier_provider="gork")
