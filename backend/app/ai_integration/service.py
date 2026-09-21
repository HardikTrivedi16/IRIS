"""
Thin wiring between the IRIS API and ``app.modules.ai``'s ``DocumentAIService``.

Contract preserved end-to-end (never flattened away by this module):
  * confidence         -> data.field_confidence / DocumentClassificationResult.confidence
  * provenance         -> data.provenance (source_id/document_name/page_number/exact_source_text)
  * evidence           -> data.field_evidence
  * source page        -> data.field_source_pages
  * human-review flag  -> requires_human_review (top-level AND per-field via low-confidence check)

Nothing here writes to Project Facts or any Document record. Turning an
extraction into an authoritative fact remains a separate, explicit action
by a human via the EXISTING ``POST /projects/{id}/facts`` endpoint — this
module has no persistence side effects at all, which is the simplest way
to guarantee "AI-extracted facts are NOT automatically authoritative."
"""
from __future__ import annotations

from app.modules.ai.exceptions import AIError, AIUnavailableError
from app.modules.ai.facade import get_ai
from app.modules.ai.schemas import DocumentType, Provenance

from . import ocr_service


class AIUnavailable(Exception):
    """Raised (and only raised) when the AI module itself reports it can't
    run right now — disabled via config, or the Ollama daemon is
    unreachable. Callers use this to return a clean 503 instead of a 500,
    without ever leaking a raw network exception."""


def ai_status() -> dict:
    ai = get_ai()
    return {
        "ai_enabled": ai.config.ai_enabled,
        "ollama_reachable": ai.core.health(),
        "generation_model": ai.config.generation_model,
        "fallback_model": ai.config.fallback_model,
        "verifier_enabled": ai.config.verifier_enabled,
        "verifier_provider": ai.config.verifier_provider,
        # Local Tesseract OCR (image -> raw text step) — independent of
        # Ollama/the LLM. See app/ai_integration/ocr_service.py.
        "ocr_available": ocr_service.is_available(),
    }


def extract_document_facts(
    text: str,
    document_type: DocumentType | str | None,
    provenance: dict | None,
) -> dict:
    ai = get_ai()
    prov = Provenance(**provenance) if provenance else None
    try:
        result = ai.documents.extract(text=text, document_type=document_type, provenance=prov)
    except AIUnavailableError as exc:
        raise AIUnavailable(str(exc)) from exc
    except AIError:
        raise  # AIInvalidOutputError etc. — a genuine 4xx-shaped caller error, let the router map it
    return result.model_dump(mode="json")


def classify_document(text: str) -> dict:
    ai = get_ai()
    try:
        result = ai.documents.classify(text=text)
    except AIUnavailableError as exc:
        raise AIUnavailable(str(exc)) from exc
    return result.model_dump(mode="json")
