"""
Pre-submission consistency check — objective data consistency only.

    GET  /api/v1/consistency/fields
    POST /api/v1/projects/{project_id}/consistency-check

The check is deterministic (``app/consistency.py``) and read-only: no LLM
decides whether values match, and nothing is written to Project Facts.
Authorization reuses ``get_project`` like every ``/projects/{id}/*`` route.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..consistency import (
    ConsistencyInputError,
    field_registry,
    project_record_observations,
    run_consistency_check,
)
from ..schemas import ConsistencyCheckRequest
from ..security import CurrentUser, get_optional_user
from ..store import get_store
from ..store.base import StoreError
from .projects import get_project

logger = logging.getLogger("iris.api.consistency")
router = APIRouter(prefix="/api/v1", tags=["consistency"])


@router.get("/consistency/fields")
def get_consistency_fields() -> dict:
    """The published comparison rule for every supported field."""
    return {"fields": field_registry()}


@router.post("/projects/{project_id}/consistency-check")
def post_consistency_check(
    project_id: str,
    body: ConsistencyCheckRequest,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)

    if body.as_of_date:
        try:
            as_of = _dt.date.fromisoformat(body.as_of_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="as_of_date must be YYYY-MM-DD")
    else:
        as_of = _dt.datetime.now(_dt.timezone.utc).date()

    observations: list[dict] = []
    if body.include_project_record:
        try:
            observations.extend(project_record_observations(get_store().get_project_facts(project_id)))
        except StoreError as exc:
            logger.error("Persistence error loading facts for %s: %s", project_id, exc)
            raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc
    observations.extend(o.model_dump() for o in body.observations)

    try:
        return run_consistency_check(observations, as_of=as_of, required_fields=body.required_fields)
    except ConsistencyInputError as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_observations", "errors": exc.errors})
