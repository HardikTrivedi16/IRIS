from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.modules.ai.schemas import DocumentType


class DocumentExtractProvenanceIn(BaseModel):
    """Caller-supplied provenance for the text being submitted. Optional —
    if omitted, the AI module still records the raw text as
    ``exact_source_text`` so the extraction is never provenance-free."""
    source_id: Optional[str] = None
    document_name: Optional[str] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    section_reference: Optional[str] = None


class DocumentExtractIn(BaseModel):
    text: str = Field(..., min_length=1, description="Document text, already OCR'd/extracted by the existing pipeline.")
    document_type: Optional[DocumentType] = None
    provenance: Optional[DocumentExtractProvenanceIn] = None


class DocumentClassifyIn(BaseModel):
    text: str = Field(..., min_length=1)


class AskIn(BaseModel):
    """Ask IRIS request body.

    ``requirement_id`` is an optional grounding hint (e.g. the requirement
    card the question was asked from). It never changes what is
    authoritative — it only narrows which live Phase 9 decisions / NetworkX
    dependency nodes are attached to the retrieval context alongside the
    indexed regulatory-source chunks. An unknown ``requirement_id`` degrades
    to grounding on every requirement in the dataset rather than erroring,
    since Ask IRIS is a best-effort read-only assistant, not a resource
    lookup.
    """
    question: str = Field(..., min_length=1, max_length=2000)
    requirement_id: Optional[str] = None
    evaluation_mode: str = Field(default="PRODUCTION", pattern="^(PRODUCTION|NON_PRODUCTION)$")
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Ad-hoc/hypothetical facts (e.g. for a 'what if X changed' question), merged "
        "on top of any facts already stored for this project (request body wins on key collision), "
        "exactly like /evaluate. These are used ONLY for this Ask IRIS answer — they are never "
        "written to this project's stored Project Facts, and the response's fact_context labels "
        "them as such so they are never presented as persisted.",
    )
    top_k: int = Field(default=5, ge=1, le=10)
