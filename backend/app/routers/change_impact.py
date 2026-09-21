"""
Project Change Impact — deterministic before/after regulatory diff.

    POST /api/v1/projects/{project_id}/change-impact

Authorization reuses ``get_project`` exactly like every other
``/projects/{id}/*`` sub-resource (tenant isolation, demo-mode handling,
404-not-401 on cross-tenant access) — this router adds no authorization
behavior of its own.

The endpoint is a PREVIEW: the proposed facts are merged onto a copy of the
project's stored facts for the duration of the request and are never
written back. ``app.change_impact`` calls ``engine_service`` directly (not
``/evaluate``), so no Decision is persisted by either side of the diff
either.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from .. import change_impact as change_impact_service
from ..fact_registry import FactValidationError
from ..schemas import ChangeImpactRequest
from ..security import CurrentUser, get_optional_user
from ..store import get_store
from ..store.base import StoreError
from .projects import get_project

logger = logging.getLogger("iris.api.change_impact")
router = APIRouter(prefix="/api/v1", tags=["change-impact"])


@router.post("/projects/{project_id}/change-impact")
def post_change_impact(
    project_id: str,
    body: ChangeImpactRequest,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)

    try:
        current_facts = get_store().get_project_facts(project_id)
    except StoreError as exc:
        logger.error("Persistence error loading facts for %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc

    try:
        return change_impact_service.analyse_change_impact(
            project_id=project_id,
            current_facts=current_facts,
            proposed_changes=body.proposed_facts,
            evaluation_mode=body.evaluation_mode,
        )
    except FactValidationError as exc:
        # Precise, per-key feedback so a form can highlight every bad field
        # at once — never a silent coercion of an ambiguous regulatory input.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_proposed_facts",
                "errors": exc.errors,
            },
        )
    except Exception as exc:  # fail safe — never leak internals
        logger.exception("Change impact analysis failed for %s", project_id)
        raise HTTPException(status_code=500, detail="Change impact analysis failed") from exc
