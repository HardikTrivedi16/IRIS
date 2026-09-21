"""
Upcoming compliance & renewals.

    GET /api/v1/projects/{project_id}/renewals?action_window_days=90&as_of=YYYY-MM-DD

Read-only. Remaining time comes only from expiry dates on record (see
``app/renewals.py``). Authorization reuses ``get_project``.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..renewals import (
    DEFAULT_ACTION_WINDOW_DAYS,
    build_renewal_register,
    records_from_confirmed_facts,
    records_from_metadata,
)
from ..security import CurrentUser, get_optional_user
from ..store import get_store
from ..store.base import StoreError
from .projects import get_project

logger = logging.getLogger("iris.api.renewals")
router = APIRouter(prefix="/api/v1", tags=["renewals"])


@router.get("/projects/{project_id}/renewals")
def get_renewals(
    project_id: str,
    action_window_days: int = Query(DEFAULT_ACTION_WINDOW_DAYS, ge=1, le=730),
    as_of: Optional[str] = None,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    if as_of:
        try:
            as_of_date = _dt.date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=422, detail="as_of must be YYYY-MM-DD")
    else:
        as_of_date = _dt.datetime.now(_dt.timezone.utc).date()

    store = get_store()
    records: list[dict] = []
    try:
        records.extend(records_from_confirmed_facts(store.get_project_facts(project_id)))
    except StoreError as exc:
        logger.error("facts unavailable for %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc
    try:
        records.extend(records_from_metadata(store.list_document_metadata(project_id)))
    except StoreError:
        # Table absent (migration 0005 not applied) — degrade to confirmed facts only.
        logger.warning("document_metadata unavailable for %s", project_id)

    return build_renewal_register(records, as_of=as_of_date, action_window_days=action_window_days)
