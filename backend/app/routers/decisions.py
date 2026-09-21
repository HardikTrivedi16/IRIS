from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..store import get_store
from ..store.base import StoreError

logger = logging.getLogger("iris.api.decisions")
router = APIRouter(prefix="/api/v1", tags=["decisions"])


@router.get("/decisions/{decision_id}")
def get_decision(decision_id: str) -> dict:
    try:
        record = get_store().get_decision(decision_id)
    except StoreError as exc:
        logger.error("Persistence error: %s", exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    return record
