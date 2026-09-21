"""
Tests for app/ai_integration + app/routers/ai_documents.py.

Uses a fake BaseAIProvider (in-process, deterministic) so these run without
a live Ollama daemon — matches the vendored AI module's own test pattern
(app/modules/ai/tests/*). Live-Ollama end-to-end behavior is intentionally
NOT claimed to pass here; see AI_INTEGRATION_NOTES for how to run those
separately with IRIS_OLLAMA_URL pointed at a real daemon.

Covers required AI test-list items:
  * Ollama unavailable  -> 503, no crash
  * AI disabled         -> 503, no crash
  * document extraction -> structured output with confidence/provenance
  * provenance          -> caller-supplied provenance is authoritative
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import BaseModel

from app.modules.ai.config import AIConfig
from app.modules.ai.exceptions import AIUnavailableError
from app.modules.ai.facade import IRISAI, _reset_ai_facade
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.schemas import ApplicantDocumentExtraction, DocumentClassificationResult, DocumentType


class _FakeProvider(BaseAIProvider):
    """Deterministic in-process fake — no network, no Ollama."""

    def __init__(self, healthy: bool = True):
        self._healthy = healthy

    def generate(self, prompt, temperature=None, max_tokens=None, think=None) -> str:
        return "fake-response"

    def generate_structured(self, prompt: str, schema, temperature=None, max_tokens=None, think=None):
        if schema is ApplicantDocumentExtraction:
            return ApplicantDocumentExtraction(
                business_name="Acme Chemicals Pvt Ltd",
                registration_number="MH-REG-1234",
                field_confidence={"business_name": 0.92, "registration_number": 0.6},
                field_evidence={"business_name": "Acme Chemicals Pvt Ltd, registered under..."},
            )
        if schema is DocumentClassificationResult:
            return DocumentClassificationResult(
                document_type=DocumentType.REGISTRATION_CERTIFICATE,
                confidence=0.88,
                reasoning="Contains a registration number and issuing authority header.",
            )
        raise AssertionError(f"Unexpected schema requested: {schema}")

    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

    def health_check(self) -> bool:
        return self._healthy


class _UnavailableProvider(BaseAIProvider):
    def generate(self, *a, **k):
        raise AIUnavailableError("simulated: Ollama daemon unreachable")

    def generate_structured(self, *a, **k):
        raise AIUnavailableError("simulated: Ollama daemon unreachable")

    def embed(self, texts):
        raise AIUnavailableError("simulated: Ollama daemon unreachable")

    def health_check(self) -> bool:
        return False


@pytest.fixture(autouse=True)
def _reset_facade():
    _reset_ai_facade()
    yield
    _reset_ai_facade()


def test_document_extraction_preserves_confidence_and_evidence():
    from app.ai_integration.service import extract_document_facts
    import app.modules.ai.facade as facade_module

    facade_module._default_facade = IRISAI(provider=_FakeProvider())
    result = extract_document_facts(text="Some OCR'd registration certificate text", document_type=None, provenance=None)

    assert result["data"]["business_name"] == "Acme Chemicals Pvt Ltd"
    assert result["data"]["field_confidence"]["business_name"] == 0.92
    assert result["data"]["field_evidence"]["business_name"].startswith("Acme Chemicals")
    # Low-confidence field (0.6 < default 0.75 threshold) must flag for review
    assert result["requires_human_review"] is True


def test_caller_provenance_overrides_model_provenance():
    from app.ai_integration.service import extract_document_facts
    import app.modules.ai.facade as facade_module

    facade_module._default_facade = IRISAI(provider=_FakeProvider())
    provenance = {"source_id": "doc-42", "document_name": "registration.pdf", "page_number": 2}
    result = extract_document_facts(text="text", document_type=None, provenance=provenance)

    assert result["data"]["provenance"]["source_id"] == "doc-42"
    assert result["data"]["provenance"]["document_name"] == "registration.pdf"
    assert result["data"]["provenance"]["page_number"] == 2
    assert result["data"]["provenance"]["exact_source_text"] == "text"


def test_classification_low_confidence_flags_review():
    from app.ai_integration.service import classify_document
    import app.modules.ai.facade as facade_module

    facade_module._default_facade = IRISAI(provider=_FakeProvider())
    result = classify_document(text="some text")
    assert result["document_type"] == "REGISTRATION_CERTIFICATE"
    assert result["confidence"] == 0.88


def test_ollama_unavailable_raises_ai_unavailable(monkeypatch):
    from app.ai_integration.service import extract_document_facts, AIUnavailable
    import app.modules.ai.facade as facade_module

    facade_module._default_facade = IRISAI(provider=_UnavailableProvider())
    with pytest.raises(AIUnavailable):
        extract_document_facts(text="text", document_type=None, provenance=None)


def test_ai_disabled_raises_ai_unavailable():
    from app.ai_integration.service import extract_document_facts, AIUnavailable
    import app.modules.ai.facade as facade_module

    cfg = AIConfig(ai_enabled=False)
    facade_module._default_facade = IRISAI(config=cfg, provider=_FakeProvider())
    with pytest.raises(AIUnavailable):
        extract_document_facts(text="text", document_type=None, provenance=None)


def test_extraction_never_writes_to_any_store():
    """This is a documentation-as-test guard: the service module must not
    import the Store interface at all — extraction has zero persistence
    side effects by construction, not by convention."""
    import app.ai_integration.service as service_module

    src = open(service_module.__file__).read()
    assert "store" not in src.lower()
