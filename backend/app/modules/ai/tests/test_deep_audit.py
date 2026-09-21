"""Contract-driven regression tests added by exhaustive AI-module audit."""
import pytest
from pydantic import BaseModel, ValidationError

from app.modules.ai import AIConfig
from app.modules.ai.exceptions import AIInvalidOutputError
from app.modules.ai.facade import IRISAI
from app.modules.ai.prompts.verification import build_verification_prompt
from app.modules.ai.providers.noop_verifier import NoOpVerifier
from app.modules.ai.retrieval.memory import InMemoryRetrievalIndex
from app.modules.ai.schemas import (
    ApplicantDocumentExtraction, GroundedAnswer, Provenance, RegulatoryCandidate,
    RegulatoryCondition, RegulatorySourceChunk, VerificationIssue, VerificationMode,
    VerificationResult, VerificationVerdict,
)
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.documents import DocumentAIService
from app.modules.ai.services.regulatory import RegulatoryAIService
from app.modules.ai.services.verification import VerificationService
from app.modules.ai.validators.safety import SafetyValidator


class NeverCalledProvider:
    def generate(self, *a, **k): raise AssertionError("provider must not be called")
    def generate_structured(self, *a, **k): raise AssertionError("provider must not be called")
    def embed(self, *a, **k): raise AssertionError("provider must not be called")
    def health_check(self): return True


def test_verification_prompt_is_task_aware_for_explanations_and_contains_schema():
    prompt = build_verification_prompt(
        "explanation_dependency", {"status": "BLOCKED"},
        {"explanation": "It is blocked.", "status": "BLOCKED"}, GroundedAnswer,
    )
    assert "JSON shapes are intentionally different" in prompt
    assert "CORRECTED_OUTPUT JSON SCHEMA" in prompt
    assert '"answer"' in prompt


def test_verification_result_rejects_incoherent_pass_with_issues():
    with pytest.raises(ValidationError):
        VerificationResult(
            verdict=VerificationVerdict.PASS,
            issues=[VerificationIssue(code="X", message="contradiction")],
        )


def test_verification_result_rejects_corrected_without_payload():
    with pytest.raises(ValidationError):
        VerificationResult(
            verdict=VerificationVerdict.CORRECTED,
            issues=[VerificationIssue(code="X", message="needs correction")],
        )


def test_noop_injection_cannot_activate_verification():
    ai = IRISAI(
        config=AIConfig(verifier_enabled=True, verifier_provider="noop"),
        provider=NeverCalledProvider(), verification_provider=NoOpVerifier(),
    )
    assert ai.verification.mode is VerificationMode.OFF
    assert ai.regulatory_verification.mode is VerificationMode.OFF


def test_document_service_rejects_empty_input_without_model_call():
    service = DocumentAIService(
        CoreAIService(NeverCalledProvider()),
        VerificationService(NoOpVerifier(), VerificationMode.OFF),
    )
    with pytest.raises(AIInvalidOutputError): service.extract("   ")
    with pytest.raises(AIInvalidOutputError): service.classify("")


def test_regulatory_service_rejects_empty_input_without_model_call():
    service = RegulatoryAIService(
        CoreAIService(NeverCalledProvider()),
        VerificationService(NoOpVerifier(), VerificationMode.OFF),
    )
    with pytest.raises(AIInvalidOutputError): service.extract_candidate("\n\t")


def test_strict_generated_schema_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ApplicantDocumentExtraction.model_validate({"business_name": "A", "invented": 1})
    with pytest.raises(ValidationError):
        RegulatoryCandidate.model_validate({"is_regulatory_requirement": False, "invented": 1})


def test_document_authorised_person_is_supported_and_confidence_checked():
    extraction = ApplicantDocumentExtraction(
        authorised_person="Asha Rao", field_confidence={"authorised_person": 0.9},
        field_evidence={"authorised_person": "Asha Rao"},
    )
    res = SafetyValidator.validate_document_extraction(extraction, "Authorised person: Asha Rao")
    assert res.valid is True


def test_document_metadata_for_unknown_field_is_not_silently_accepted():
    extraction = ApplicantDocumentExtraction(field_confidence={"made_up": 0.9})
    res = SafetyValidator.validate_document_extraction(extraction, "text")
    assert res.requires_human_review is True
    assert any(i.code == "UNKNOWN_EXTRACTION_METADATA_FIELD" for i in res.issues)


def test_inmemory_index_rejects_non_numeric_and_boolean_embeddings():
    idx = InMemoryRetrievalIndex()
    chunk = RegulatorySourceChunk(chunk_id="c", source_id="s", text="x")
    with pytest.raises(AIInvalidOutputError): idx.add(chunk, [1.0, "bad"])  # type: ignore[list-item]
    with pytest.raises(AIInvalidOutputError): idx.add(chunk, [1.0, True])


def test_page_numbers_are_one_based_in_provenance():
    with pytest.raises(ValidationError): Provenance(page_number=0)
