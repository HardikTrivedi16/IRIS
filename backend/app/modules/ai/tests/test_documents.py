"""Tests for DocumentAIService in IRIS AI Module."""

import sys
from typing import Any
from unittest.mock import MagicMock
import pytest

from app.modules.ai import (
    AIConfig,
    ApplicantDocumentExtraction,
    DocumentClassificationResult,
    DocumentExtractionResult,
    DocumentType,
    ExtractedFact,
    Provenance,
    VerificationIssue,
    VerificationMode,
    VerificationOutcome,
    VerificationResult,
    VerificationVerdict,
    _reset_ai_facade,
    get_ai,
)
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.services.core import CoreAIService
from app.modules.ai.services.documents import DocumentAIService
from app.modules.ai.services.verification import VerificationService


class MockDocAIProvider(BaseAIProvider):
    """Mock Core AI Provider returning predetermined structured objects."""

    def __init__(self, structured_return: Any = None) -> None:
        self.structured_return = structured_return
        self.last_prompt = ""

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return "mock text"

    def generate_structured(self, prompt: str, schema: type[Any], **kwargs: Any) -> Any:
        self.last_prompt = prompt
        return self.structured_return

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def health_check(self) -> bool:
        return True


class MockDocVerifier(BaseVerificationProvider):
    """Mock Verification Provider for DocumentAIService."""

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
# TEST AI-DOC-01: Structured applicant extraction preserves standard facts
# ==============================================================================
def test_ai_doc_01_structured_applicant_extraction_preserves_facts():
    expected_doc = ApplicantDocumentExtraction(
        business_name="ABC Foods Pvt Ltd",
        capacity_value=80.0,
        capacity_unit="TPD",
        location="Pune, Maharashtra",
        state="Maharashtra",
        district="Pune",
        registration_number="FP-2026-1042",
        valid_until="2027-03-31",
        worker_count=45,
        field_confidence={
            "business_name": 0.99, "capacity_value": 0.99, "capacity_unit": 0.99,
            "location": 0.99, "state": 0.99, "district": 0.99,
            "registration_number": 0.99, "valid_until": 0.99, "worker_count": 0.99,
        },
    )
    provider = MockDocAIProvider(structured_return=expected_doc)
    core = CoreAIService(provider=provider)
    verifier = MockDocVerifier()
    verification = VerificationService(provider=verifier, mode=VerificationMode.ADVISORY)
    doc_service = DocumentAIService(core=core, verification=verification)

    raw_text = """
    ABC Foods Pvt Ltd
    Installed Production Capacity: 80 TPD
    Project Location: Pune, Maharashtra
    Registration Number: FP-2026-1042
    Valid Until: 31-03-2027
    Number of Workers: 45
    """
    res = doc_service.extract(text=raw_text)

    assert isinstance(res, DocumentExtractionResult)
    assert res.data.business_name == "ABC Foods Pvt Ltd"
    assert res.data.capacity_value == 80.0
    assert res.data.capacity_unit == "TPD"
    assert res.data.location == "Pune, Maharashtra"
    assert res.data.registration_number == "FP-2026-1042"
    assert res.data.valid_until == "2027-03-31"
    assert res.data.worker_count == 45
    assert res.safety_valid is True
    assert res.requires_human_review is False


# ==============================================================================
# TEST AI-DOC-02: Missing fields remain null rather than being invented
# ==============================================================================
def test_ai_doc_02_missing_fields_remain_null():
    partial_doc = ApplicantDocumentExtraction(
        business_name="XYZ Warehousing",
        location="Nagpur, Maharashtra",
        worker_count=None,
        capacity_value=None,
        valid_until=None,
    )
    provider = MockDocAIProvider(structured_return=partial_doc)
    core = CoreAIService(provider=provider)
    verification = VerificationService(provider=MockDocVerifier(), mode=VerificationMode.OFF)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.extract("XYZ Warehousing located in Nagpur, Maharashtra.")
    assert res.data.business_name == "XYZ Warehousing"
    assert res.data.worker_count is None
    assert res.data.capacity_value is None
    assert res.data.valid_until is None


# ==============================================================================
# TEST AI-DOC-03: Negative impossible worker count is rejected/marked unsafe
# ==============================================================================
def test_ai_doc_03_negative_worker_count_marked_unsafe():
    bad_doc = ApplicantDocumentExtraction(
        business_name="Defect Unit",
        worker_count=-15,
    )
    provider = MockDocAIProvider(structured_return=bad_doc)
    core = CoreAIService(provider=provider)
    verification = VerificationService(provider=MockDocVerifier(), mode=VerificationMode.OFF)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.extract("Defect text with -15 workers")
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert any("NEGATIVE_WORKER_COUNT" in w for w in res.warnings)


# ==============================================================================
# TEST AI-DOC-04: Negative capacity is rejected/marked unsafe
# ==============================================================================
def test_ai_doc_04_negative_capacity_marked_unsafe():
    bad_doc = ApplicantDocumentExtraction(
        business_name="Defect Unit",
        capacity_value=-50.0,
    )
    provider = MockDocAIProvider(structured_return=bad_doc)
    core = CoreAIService(provider=provider)
    verification = VerificationService(provider=MockDocVerifier(), mode=VerificationMode.OFF)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.extract("Defect text with negative capacity")
    assert res.safety_valid is False
    assert res.requires_human_review is True
    assert any("NEGATIVE_CAPACITY" in w for w in res.warnings)


# ==============================================================================
# TEST AI-DOC-05: Classification can return UNKNOWN
# ==============================================================================
def test_ai_doc_05_classification_returns_unknown():
    class_return = DocumentClassificationResult(
        document_type=DocumentType.UNKNOWN,
        confidence=0.1,
        reasoning="Unintelligible text without standard headers.",
        requires_human_review=True,
    )
    provider = MockDocAIProvider(structured_return=class_return)
    core = CoreAIService(provider=provider)
    verification = VerificationService(provider=MockDocVerifier(), mode=VerificationMode.OFF)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.classify("Garbled text snippet")
    assert res.document_type == DocumentType.UNKNOWN
    assert res.requires_human_review is True


# ==============================================================================
# TEST AI-DOC-06: Classification does not imply legal validity
# ==============================================================================
def test_ai_doc_06_classification_does_not_imply_legal_validity():
    class_return = DocumentClassificationResult(
        document_type=DocumentType.ENVIRONMENTAL_CONSENT,
        confidence=0.92,
        reasoning="Document states 'Consent to Establish' header.",
        requires_human_review=False,
    )
    provider = MockDocAIProvider(structured_return=class_return)
    core = CoreAIService(provider=provider)
    verification = VerificationService(provider=MockDocVerifier(), mode=VerificationMode.OFF)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.classify("CTE Header text")
    assert res.document_type == DocumentType.ENVIRONMENTAL_CONSENT
    # The result has only classification semantics, no approval/validity fields
    assert not hasattr(res, "is_valid")
    assert not hasattr(res, "approved")


# ==============================================================================
# TEST AI-DOC-07: ADVISORY verifier correction incorporated after schema validation
# ==============================================================================
def test_ai_doc_07_advisory_verifier_correction_incorporated():
    local_doc = ApplicantDocumentExtraction(
        business_name="ABC Foods",
        capacity_value=2.0,  # model saw 2:00
        capacity_unit="TPD",
    )
    provider = MockDocAIProvider(structured_return=local_doc)
    core = CoreAIService(provider=provider)

    corrected_doc = ApplicantDocumentExtraction(
        business_name="ABC Foods",
        capacity_value=20.0,  # verifier fixed to 20
        capacity_unit="TPD",
    )
    verifier = MockDocVerifier(
        result=VerificationResult(
            verdict=VerificationVerdict.CORRECTED,
            issues=[VerificationIssue(code="NUMERIC_FIDELITY", field="capacity_value", message="Fixed 2 to 20")],
            corrected_output=corrected_doc,
            verifier_provider="mock_groq",
        )
    )
    verification = VerificationService(provider=verifier, mode=VerificationMode.ADVISORY)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.extract("ABC Foods capacity 20 TPD")
    assert res.data.capacity_value == 20.0
    assert res.outcome.corrected_by_verifier is True
    assert res.safety_valid is True


# ==============================================================================
# TEST AI-DOC-08: ADVISORY verifier rejection results in requires_human_review
# ==============================================================================
def test_ai_doc_08_advisory_rejection_requires_human_review():
    local_doc = ApplicantDocumentExtraction(
        business_name="Hallucinated Entity",
        registration_number="NOC-9999",
    )
    provider = MockDocAIProvider(structured_return=local_doc)
    core = CoreAIService(provider=provider)

    verifier = MockDocVerifier(
        result=VerificationResult(
            verdict=VerificationVerdict.REJECT,
            issues=[VerificationIssue(code="UNSUPPORTED_DATA", field="registration_number", message="Registration not in text")],
            corrected_output=None,
            verifier_provider="mock_groq",
        )
    )
    verification = VerificationService(provider=verifier, mode=VerificationMode.ADVISORY)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.extract("Text with no registration")
    assert res.outcome.result.verdict == VerificationVerdict.REJECT
    assert res.requires_human_review is True
    assert any("UNSUPPORTED_DATA" in w for w in res.warnings)


# ==============================================================================
# TEST AI-DOC-09: Verifier unavailability in ADVISORY does not crash extraction
# ==============================================================================
def test_ai_doc_09_verifier_unavailability_does_not_crash():
    local_doc = ApplicantDocumentExtraction(
        business_name="Safe Co",
        worker_count=20,
    )
    provider = MockDocAIProvider(structured_return=local_doc)
    core = CoreAIService(provider=provider)

    from app.modules.ai.exceptions import AIUnavailableError
    verifier = MockDocVerifier(exc=AIUnavailableError("Groq offline"))
    verification = VerificationService(provider=verifier, mode=VerificationMode.ADVISORY)
    doc_service = DocumentAIService(core=core, verification=verification)

    res = doc_service.extract("Safe Co text")
    assert res.data.business_name == "Safe Co"
    assert res.outcome.verification_performed is False
    assert res.requires_human_review is True
    assert any("Groq offline" in w for w in res.warnings)


# ==============================================================================
# TEST AI-DOC-10: Document service does not import business Documents module
# ==============================================================================
def test_ai_doc_10_no_business_module_imports():
    from app.modules.ai.services import documents
    import inspect

    source_code = inspect.getsource(documents)
    assert "DocumentsService" not in source_code
    assert "app.modules.documents" not in source_code
    assert "RuleEngineService" not in source_code
    assert "ProjectsService" not in source_code


# ==============================================================================
# OPTIONAL LIVE PHASE 3 SMOKE TEST
# Skipped by default. Run manually with:
# pytest app/modules/ai/tests/test_documents.py -v -m "live_phase3"
# ==============================================================================
@pytest.mark.live_phase3
def test_live_phase3_document_extraction_smoke():
    ai = get_ai()
    if not ai.core.health():
        pytest.skip("Local Ollama daemon is not reachable at configured URL")

    synthetic_text = """
    ABC Foods Pvt Ltd
    Installed Production Capacity: 80 TPD
    Project Location: Pune, Maharashtra
    Registration Number: FP-2026-1042
    Valid Until: 31-03-2027
    Number of Workers: 45
    """
    res = ai.documents.extract(synthetic_text)
    assert res.data.business_name is not None
    assert res.data.capacity_value == 80.0
    assert res.safety_valid is True

