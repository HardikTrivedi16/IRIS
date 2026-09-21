from __future__ import annotations

from fastapi import APIRouter

from .. import engine_service
from ..config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    try:
        ds = engine_service.get_dataset()
        dataset_ok = True
        requirement_count = len(ds.requirements)
    except Exception:  # dataset failed to load — report, don't crash /health
        dataset_ok = False
        requirement_count = 0
    return {
        "status": "ok" if dataset_ok else "degraded",
        "engine_dataset_loaded": dataset_ok,
        "requirement_count": requirement_count,
        "persistence_backend": "supabase" if settings.supabase_configured else "memory",
    }
