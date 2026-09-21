from __future__ import annotations

import logging
from functools import lru_cache

from ..config import get_settings
from .base import Store
from .memory_store import MemoryStore

logger = logging.getLogger("iris.store")


@lru_cache
def get_store() -> Store:
    settings = get_settings()
    if settings.supabase_configured:
        from .supabase_store import SupabaseStore  # imported lazily: httpx only needed here

        logger.info("Persistence backend: Supabase (%s)", settings.supabase_url)
        return SupabaseStore(
            url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            schema=settings.supabase_schema,
        )
    logger.warning(
        "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — using the in-memory "
        "store. Projects, facts and decisions will NOT survive a process "
        "restart. Set both env vars (see backend/.env.example) to persist to "
        "Supabase."
    )
    return MemoryStore()


__all__ = ["get_store", "Store"]
