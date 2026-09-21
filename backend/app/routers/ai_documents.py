"""
AI / document-intelligence endpoints (Phase 4-5 of the AI integration).

    GET  /api/v1/ai/status
    POST /api/v1/projects/{project_id}/documents/extract
    POST /api/v1/projects/{project_id}/documents/classify

Authorization reuses ``get_project`` exactly like every other
``/projects/{id}/*`` sub-resource. ``/ai/status`` is deliberately
unauthenticated/project-independent — it reports module-level
availability only (enabled flag, Ollama reachability, configured model
names), never project or applicant data.

Nothing here calls the Phase 9 Rule Engine or writes to Project Facts.
AI-extracted values only become authoritative Project Facts when a human
explicitly submits them via the existing ``POST /projects/{id}/facts``
endpoint — this router never does that on the caller's behalf.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..ai_integration.schemas import DocumentClassifyIn, DocumentExtractIn
from ..ai_integration.service import ai_status, classify_document, extract_document_facts, AIUnavailable
from ..security import CurrentUser, get_optional_user
from app.modules.ai.exceptions import AIInvalidOutputError
from .projects import get_project

logger = logging.getLogger("iris.api.ai_documents")
router = APIRouter(prefix="/api/v1", tags=["ai-documents"])


@router.get("/ai/status")
def get_ai_status() -> dict:
    return ai_status()


@router.post("/projects/{project_id}/documents/extract")
def post_extract_document(
    project_id: str,
    body: DocumentExtractIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    try:
        return extract_document_facts(
            text=body.text,
            document_type=body.document_type,
            provenance=body.provenance.model_dump(exclude_none=True) if body.provenance else None,
        )
    except AIUnavailable as exc:
        logger.warning("AI unavailable for document extraction on %s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail="AI document extraction is currently unavailable.")
    except AIInvalidOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Document extraction failed for %s", project_id)
        raise HTTPException(status_code=500, detail="Document extraction failed")


@router.post("/projects/{project_id}/documents/classify")
def post_classify_document(
    project_id: str,
    body: DocumentClassifyIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    try:
        return classify_document(text=body.text)
    except AIUnavailable as exc:
        logger.warning("AI unavailable for document classification on %s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail="AI document classification is currently unavailable.")
    except AIInvalidOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Document classification failed for %s", project_id)
        raise HTTPException(status_code=500, detail="Document classification failed")
