"""
Backend configuration.

All values are read from environment variables (see backend/.env.example).
Nothing here hardcodes a secret. If SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
are not both set, the API falls back to an in-memory store so the backend
and the Phase 9 engine can still be exercised locally / in CI without a
live Supabase project (see app/store/__init__.py).

Authentication (Supabase Auth integration)
------------------------------------------
The backend verifies Supabase JWT tokens using JWKS (RS256) by default.
The JWKS endpoint is derived automatically from SUPABASE_URL:
    {SUPABASE_URL}/auth/v1/keys

If SUPABASE_JWT_SECRET is also set, it is used as a fallback for HS256
tokens (older Supabase projects that have not switched to RS256).

If SUPABASE_URL is not configured, the API runs in demo mode: auth is
disabled, a static demo user is returned for all requests. This is
intentionally limited to local/dev/CI usage. Never run in demo mode
on a production deployment.

Security note: SUPABASE_SERVICE_ROLE_KEY and SUPABASE_JWT_SECRET are
server-only secrets — they are only ever read here, in backend code, and
are never sent to the frontend build or included in any API response.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env explicitly by absolute path (this file is backend/app/config.py,
# so parent.parent is backend/) — this works regardless of the process's current
# working directory when uvicorn is started. Real OS environment variables (e.g. set
# via `$env:VAR = ...` in PowerShell) still take precedence: load_dotenv() defaults to
# override=False, so it only fills in variables that aren't already set.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    def __init__(self) -> None:
        self.regulatory_data_root: str = os.environ.get("REGULATORY_DATA_ROOT", "regulatory-data")
        # Verified scheme catalogue (docs/SCHEME_CATALOGUE_INPUT_REQUIREMENTS.md).
        # Ships EMPTY: no scheme content exists until research delivers it.
        self.scheme_data_root: str = os.environ.get("SCHEME_DATA_ROOT", "scheme-data")
        self.supabase_url: str | None = os.environ.get("SUPABASE_URL") or None
        self.supabase_service_role_key: str | None = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None
        self.supabase_schema: str = os.environ.get("SUPABASE_SCHEMA", "public")
        self.supabase_jwt_secret: str | None = os.environ.get("SUPABASE_JWT_SECRET") or None
        self.cors_origins: list[str] = _split_csv(
            os.environ.get("CORS_ORIGINS"),
            default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
        )
        self.api_title: str = "IRIS Regulatory Engine API"
        # Explicit Demo Mode flag.
        # In production, this MUST be false (the default). Missing Supabase configuration
        # or missing auth tokens will fail closed with HTTP 500 / 401 instead of granting
        # Demo Officer access. Demo mode is never inferred automatically.
        self.iris_demo_mode: bool = os.environ.get("IRIS_DEMO_MODE", "false").lower() in ("true", "1", "yes")


    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def auth_configured(self) -> bool:
        """True when Supabase Auth JWT verification is possible.
        Requires at minimum SUPABASE_URL (for JWKS endpoint).
        SUPABASE_JWT_SECRET adds HS256 fallback support."""
        return bool(self.supabase_url)

    @property
    def jwks_url(self) -> str | None:
        """URL of the Supabase JWKS endpoint for asymmetric (RS256/ES256) token
        verification.

        Modern Supabase projects sign user access tokens with rotating
        asymmetric keys (commonly ES256) and publish the public JWKS at the
        standard well-known path:

            {SUPABASE_URL}/auth/v1/.well-known/jwks.json

        This endpoint is public (no apikey required). The older
        ``/auth/v1/keys`` path used by some legacy integrations 404s on these
        projects, which previously caused every authenticated request to fail
        with 401 (the ES256 token could match neither the missing JWKS nor the
        legacy HS256 secret)."""
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
