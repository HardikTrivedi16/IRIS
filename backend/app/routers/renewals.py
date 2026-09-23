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
from ..legacy_evidence import is_legacy_metadata_row, legacy_info
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
    legacy_excluded = 0
    try:
        metadata_rows = store.list_document_metadata(project_id)
        current_rows = [r for r in metadata_rows if not is_legacy_metadata_row(project_id, r)]
        legacy_excluded = len(metadata_rows) - len(current_rows)
        records.extend(records_from_metadata(current_rows))
    except StoreError:
        # Table absent (migration 0005 not applied) — degrade to confirmed facts only.
        logger.warning("document_metadata unavailable for %s", project_id)

    register = build_renewal_register(records, as_of=as_of_date, action_window_days=action_window_days)
    register["legacy_documents_excluded"] = legacy_excluded
    if legacy_excluded:
        info = legacy_info(project_id) or {}
        register.setdefault("notes", []).append(
            f"{legacy_excluded} legacy document(s) describing the prior facility "
            f"({info.get('prior_facility', 'prior facility')}) are excluded: their expiry dates are not "
            "obligations of the current facility. They remain listed in the Document Register."
        )
    return register
