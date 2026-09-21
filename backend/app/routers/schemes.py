"""
Scheme framework endpoints (P2-K). Software only — see ``app/schemes.py``.

    GET /api/v1/schemes/catalogue
    GET /api/v1/projects/{project_id}/schemes?mode=PRODUCTION|NON_PRODUCTION

Eligibility is matched deterministically from the project's STORED Project
Facts; no LLM decides anything. With no ACTIVE + VERIFIED catalogue records
(the shipped state) the result is AWAITING_VERIFIED_DATA with no results.
"""
from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..engine_service import BACKEND_DIR
from ..schemes import load_catalogue, match_catalogue
from ..security import CurrentUser, get_optional_user
from ..store import get_store
from ..store.base import StoreError
from .projects import get_project

logger = logging.getLogger("iris.api.schemes")
router = APIRouter(prefix="/api/v1", tags=["schemes"])


def _catalogue():
    root = get_settings().scheme_data_root
    root = root if os.path.isabs(root) else os.path.join(BACKEND_DIR, root)
    return load_catalogue(root)


@router.get("/schemes/catalogue")
def get_catalogue() -> dict:
    cat = _catalogue()
    return {
        "catalogue_state": "INVALID" if cat.errors else ("READY" if cat.usable else "AWAITING_VERIFIED_DATA"),
        "counts": {"total": len(cat.schemes), "active_verified": len(cat.usable)},
        "catalogue_errors": cat.errors,
    }


@router.get("/projects/{project_id}/schemes")
def get_project_schemes(
    project_id: str,
    mode: Literal["PRODUCTION", "NON_PRODUCTION"] = "PRODUCTION",
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    try:
        facts = get_store().get_project_facts(project_id)
    except StoreError as exc:
        logger.error("facts unavailable for %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc
    return match_catalogue(_catalogue(), facts, mode=mode)
