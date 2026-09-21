"""
Local Tesseract OCR endpoint — image bytes -> raw text only.

    POST /api/v1/projects/{project_id}/documents/ocr

This is NOT the AI/LLM extraction step and NOT a second document-extraction
system. It only turns an uploaded image into raw text via local Tesseract;
the existing, unchanged POST /projects/{id}/documents/extract endpoint is
still the step that produces structured fields with confidence/evidence,
and only an explicit human confirmation via the existing
POST /projects/{id}/facts endpoint persists anything. Nothing here writes
to Project Facts or any Document record.

Authorization reuses ``get_project`` exactly like every other
``/projects/{id}/*`` sub-resource — no new authorization behavior.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..ai_integration.ocr_service import (
    OCRInvalidInput,
    OCRUnavailable,
    extract_text_from_image,
)
from ..security import CurrentUser, get_optional_user
from .projects import get_project

logger = logging.getLogger("iris.api.ocr")
router = APIRouter(prefix="/api/v1", tags=["ocr"])


@router.post("/projects/{project_id}/documents/ocr")
async def post_ocr(
    project_id: str,
    file: UploadFile = File(...),
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    try:
        image_bytes = await file.read()
        return extract_text_from_image(image_bytes, file.content_type)
    except OCRInvalidInput as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OCRUnavailable as exc:
        logger.warning("OCR unavailable for %s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("OCR request failed for %s", project_id)
        raise HTTPException(status_code=500, detail="OCR request failed") from exc
