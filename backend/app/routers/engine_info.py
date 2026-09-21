from __future__ import annotations

from fastapi import APIRouter

from .. import engine_service

router = APIRouter(prefix="/api/v1", tags=["engine"])


@router.get("/engine")
def get_engine_info() -> dict:
    return engine_service.engine_info()
