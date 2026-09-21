"""
Ask IRIS — read-only, grounded regulatory Q&A endpoint.

    POST /api/v1/projects/{project_id}/ask

Authorization reuses ``get_project`` exactly like every other
``/projects/{id}/*`` sub-resource (tenant isolation, demo-mode handling,
404-not-401-leak on cross-tenant access) — this router adds no new
authorization behavior of its own.

This endpoint never evaluates anything itself: it merges facts exactly like
``/evaluate`` (``_merged_facts``) and delegates all reasoning to
``app.ai_integration.ask_service.ask_iris``, which calls the frozen Phase 9
engine and NetworkX dependency graph directly and only uses the AI module to
explain — never to decide. See ``ask_service`` module docstring.

``body.facts`` (if any) is also passed through separately as
``hypothetical_facts`` so the response can label which values were ad-hoc
overrides for this question rather than this project's stored Project
Facts. Nothing here writes ``body.facts`` to the store — the merge used for
evaluation (``_merged_facts``) is unchanged and remains read-only, exactly
like ``/evaluate``.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.modules.ai.exceptions import AIInvalidOutputError

from ..ai_integration.ask_service import AIUnavailable, ask_iris
from ..ai_integration.schemas import AskIn
from ..security import CurrentUser, get_optional_user
from ..store.base import StoreError
from .evaluate import _merged_facts
from .projects import get_project

logger = logging.getLogger("iris.api.ask")
router = APIRouter(prefix="/api/v1", tags=["ask-iris"])


@router.post("/projects/{project_id}/ask")
def post_ask(
    project_id: str,
    body: AskIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    # Same tenant-isolation/demo-mode/role logic as every other
    # /projects/{id}/* endpoint — raises 401/404 as appropriate.
    get_project(project_id, user=user)

    facts = _merged_facts(project_id, body.facts)
    try:
        return ask_iris(
            project_id=project_id,
            question=body.question,
            facts=facts,
            requirement_id=body.requirement_id,
            evaluation_mode=body.evaluation_mode,
            top_k=body.top_k,
            hypothetical_facts=body.facts,
        )
    except AIUnavailable as exc:
        logger.warning("AI unavailable for Ask IRIS on %s: %s", project_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Ask IRIS is currently unavailable (AI service unreachable).",
        )
    except AIInvalidOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except StoreError as exc:
        logger.error("Persistence error for Ask IRIS on %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable")
    except Exception as exc:  # fail safe — never leak internals
        logger.exception("Ask IRIS failed for %s", project_id)
        raise HTTPException(status_code=500, detail="Ask IRIS request failed") from exc
