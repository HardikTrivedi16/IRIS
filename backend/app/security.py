"""
Security: Supabase Auth JWT verification + role-based access control.

Authentication Strategy
------------------------
1. JWKS (RS256) — preferred. JWKS fetched from {SUPABASE_URL}/auth/v1/keys
   and cached for 1 hour. No JWT secret needed; only the Supabase project URL.

2. HS256 fallback — used if SUPABASE_JWT_SECRET is set and RS256 verification
   fails (e.g., older Supabase projects using JWT secret signing).

3. Demo mode — if SUPABASE_URL is not configured, returns a static demo user.
   A warning is logged. MUST NOT be used in production.

JWT Verification Flow
----------------------
  Authorization: Bearer <supabase_jwt>
  ↓
  Extract header → get kid
  ↓
  Fetch JWKS (cached, 1h TTL) → find matching key
  ↓
  jose.jwt.decode(token, key, algorithms=["RS256"])
  ↓
  payload.sub → look up user_profiles table (via department_store or inline)
  ↓
  Build CurrentUser(user_id, email, role, department_id)

Backend Role Enforcement
--------------------------
  INDUSTRY_USER      → can call /api/v1/* (engine, projects, evaluate)
                       CANNOT call /api/v1/department/* or /api/v1/auth/me
  DEPARTMENT_OFFICER → can call /api/v1/department/* (read + transitions)
  DEPARTMENT_MANAGER → can call /api/v1/department/* + assign/reassign
  DEPARTMENT_ADMIN   → full department access + SLA policy management + user mgmt

Security guarantees
--------------------
* SUPABASE_SERVICE_ROLE_KEY is NEVER in any response or accessible from frontend.
* SUPABASE_JWT_SECRET is NEVER in any response (server-only fallback).
* JWKS keys are public-key material only (safe to cache).
* Demo mode logs a WARNING on every request; cannot be silently deployed.
* Role checks are enforced at the backend HTTP layer, not frontend routing alone.

Remaining limitations (documented, not pretended away)
--------------------------------------------------------
* Full industry project isolation requires a user_id FK on the projects table,
  which is a known prerequisite (see migration 0003 comment on projects_read_authenticated).
  Until that migration is applied, authenticated industry users can read all projects.
* JWKS cache is in-process memory; a multi-worker deployment needs a shared cache
  (Redis or similar). For single-worker deployments this is fine.
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request

logger = logging.getLogger("iris.auth")


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class Role(str, Enum):
    INDUSTRY_USER = "INDUSTRY_USER"
    DEPARTMENT_OFFICER = "DEPARTMENT_OFFICER"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"


GOVERNMENT_ROLES = {Role.DEPARTMENT_OFFICER, Role.DEPARTMENT_MANAGER, Role.DEPARTMENT_ADMIN}


# ---------------------------------------------------------------------------
# Current user model
# ---------------------------------------------------------------------------

class CurrentUser:
    """Verified user identity, derived from a Supabase JWT."""

    def __init__(
        self,
        user_id: str,
        email: Optional[str],
        role: Role,
        department_id: Optional[str] = None,
        name: Optional[str] = None,
        is_demo: bool = False,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role
        self.department_id = department_id
        self.name = name or email or user_id
        self.is_demo = is_demo

    def has_role(self, *roles: Role) -> bool:
        return self.role in roles

    def is_government(self) -> bool:
        return self.role in GOVERNMENT_ROLES

    def is_industry(self) -> bool:
        return self.role == Role.INDUSTRY_USER

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role.value,
            "department_id": self.department_id,
            "name": self.name,
            "is_demo": self.is_demo,
        }


# Demo user — used ONLY when IRIS_DEMO_MODE=true is explicitly configured
# Default department is dept-mpcb to align with seeded operational data.
_DEMO_USER = CurrentUser(
    user_id="demo-officer-001",
    email="demo@iris.local",
    role=Role.DEPARTMENT_ADMIN,
    department_id="dept-mpcb",
    name="Demo Officer",
    is_demo=True,
)


# ---------------------------------------------------------------------------
# JWKS cache (in-process, 1-hour TTL)
# ---------------------------------------------------------------------------

_jwks_cache: dict = {"keys": None, "expires_at": 0.0}
_JWKS_TTL_SECONDS = 3600  # 1 hour


def _fetch_jwks(jwks_url: str, apikey: Optional[str] = None) -> dict:
    """Fetch JWKS from Supabase and cache for 1 hour.

    Supabase's /auth/v1/keys endpoint requires the project ``apikey`` header;
    without it the endpoint responds 401. Projects that never enabled
    asymmetric (RS256/ES256) signing keys respond 404 here — in that case the
    project signs tokens with the legacy HS256 JWT secret and this endpoint is
    simply unused (verification falls back to HS256).
    """
    now = time.monotonic()
    if _jwks_cache["keys"] is not None and now < _jwks_cache["expires_at"]:
        return _jwks_cache["keys"]
    try:
        headers = {"apikey": apikey} if apikey else {}
        resp = httpx.get(jwks_url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        keys = resp.json()
        _jwks_cache["keys"] = keys
        _jwks_cache["expires_at"] = now + _JWKS_TTL_SECONDS
        logger.info("JWKS fetched and cached from %s (%d keys)", jwks_url, len(keys.get("keys", [])))
        return keys
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", jwks_url, exc)
        # Return stale cache if available, otherwise raise
        if _jwks_cache["keys"] is not None:
            logger.warning("Using stale JWKS cache")
            return _jwks_cache["keys"]
        raise


def _verify_jwt(
    token: str,
    jwks_url: str,
    jwt_secret: Optional[str] = None,
    apikey: Optional[str] = None,
) -> dict:
    """
    Verify a Supabase JWT.

    Supabase projects fall into two camps:
      - Legacy HS256: access tokens are signed symmetrically with the project
        JWT secret (SUPABASE_JWT_SECRET). There is no JWKS endpoint (it 404s).
      - Asymmetric RS256/ES256: tokens are signed with rotating keys published
        at {SUPABASE_URL}/auth/v1/keys (JWKS).

    Strategy: if a JWT secret is configured, try HS256 FIRST — it is a pure
    in-process check with no network call, and is this project's signing
    method. Only if that fails (or no secret is configured) do we fetch the
    JWKS and try the asymmetric algorithms. This avoids a failing network
    round-trip on every request for legacy HS256 projects.

    Returns the decoded payload dict on success.
    Raises ValueError with a safe (non-leaking) message on failure.
    """
    # Import here to keep the import lazy (python-jose is optional for demo mode)
    try:
        from jose import jwt as jose_jwt, JWTError  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "python-jose[cryptography] is not installed. "
            "Run: pip install 'python-jose[cryptography]>=3.3'"
        )

    # Attempt 1: HS256 via JWT secret (legacy Supabase projects — this project).
    hs256_error: Optional[str] = None
    if jwt_secret:
        try:
            return jose_jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except Exception as exc:
            hs256_error = str(exc)
            logger.debug("HS256 verification failed: %s", hs256_error)
    else:
        hs256_error = "SUPABASE_JWT_SECRET not configured"

    # Attempt 2: RS256/ES256 via JWKS (asymmetric-key Supabase projects).
    rs256_error: Optional[str] = None
    try:
        jwks = _fetch_jwks(jwks_url, apikey=apikey)
        return jose_jwt.decode(
            token,
            jwks,
            algorithms=["RS256", "ES256"],
            options={"verify_aud": False},
        )
    except Exception as exc:
        rs256_error = str(exc)
        # Bumped from debug so the real failure reason (bad secret, expired
        # token, malformed token, missing JWKS, etc.) is visible in server
        # logs instead of only the generic 401 the client receives. Never
        # sent to the client either way.
        logger.warning(
            "JWT verification failed (HS256: %s; JWKS/RS256/ES256: %s)",
            hs256_error,
            rs256_error,
        )

    raise ValueError(f"JWT verification failed (HS256: {hs256_error}; JWKS: {rs256_error})")


# ---------------------------------------------------------------------------
# Profile lookup helper
# ---------------------------------------------------------------------------

def _build_user_from_payload(payload: dict, department_store=None) -> CurrentUser:
    """
    Build a CurrentUser from a verified JWT payload.

    Looks up the user's IRIS role and department from the department store
    (user_profiles / department_users). Falls back to INDUSTRY_USER if no
    profile is found (first-time login case; profile created via POST /api/v1/auth/profile).
    """
    sub = payload.get("sub")
    if not sub:
        raise ValueError("JWT missing sub claim")

    email = payload.get("email") or payload.get("user_metadata", {}).get("email")
    name = (
        payload.get("user_metadata", {}).get("full_name")
        or payload.get("user_metadata", {}).get("name")
        or email
    )

    if department_store is not None:
        # Look up IRIS profile
        profile = department_store.get_user_profile_by_auth_uid(sub)
        if profile:
            role = Role(profile.get("iris_role", Role.INDUSTRY_USER.value))
            dept_id = profile.get("department_id")
            return CurrentUser(
                user_id=sub,
                email=email,
                role=role,
                department_id=dept_id,
                name=profile.get("full_name") or name,
            )

    # No profile yet — treat as INDUSTRY_USER (profile will be created at /api/v1/auth/profile)
    return CurrentUser(
        user_id=sub,
        email=email,
        role=Role.INDUSTRY_USER,
        department_id=None,
        name=name,
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _extract_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def get_current_user(request: Request) -> CurrentUser:
    """
    FastAPI dependency: verify Supabase JWT and return the current user.

    Behaviour by configuration:
      - SUPABASE_URL set → real JWT verification (JWKS/RS256, HS256 fallback)
      - SUPABASE_URL not set AND IRIS_DEMO_MODE=true → demo mode (DemoUser returned, WARNING logged)
      - SUPABASE_URL not set AND IRIS_DEMO_MODE=false → FAILS CLOSED (HTTP 500 error)

    Demo mode is never inferred automatically. In production, missing auth
    configuration or unauthenticated requests fail closed.
    """
    from .config import get_settings
    from .store.department_store import get_department_store

    settings = get_settings()

    if not settings.auth_configured:
        if not settings.iris_demo_mode:
            logger.error(
                "Authentication failed: Supabase is not configured and IRIS_DEMO_MODE is not true. "
                "Failing closed in production."
            )
            raise HTTPException(
                status_code=500,
                detail="Authentication service unavailable. Server must have IRIS_DEMO_MODE=true for local demo mode.",
            )
        logger.warning(
            "IRIS running in AUTH DEMO MODE (IRIS_DEMO_MODE=true). "
            "All requests treated as Demo Officer. DO NOT use in production."
        )
        return _DEMO_USER

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token. Include 'Authorization: Bearer <token>' header.",
        )

    try:
        payload = _verify_jwt(
            token,
            jwks_url=settings.jwks_url,
            jwt_secret=settings.supabase_jwt_secret,
            apikey=settings.supabase_service_role_key,
        )
    except ValueError as exc:
        logger.info("JWT verification failed for request to %s: %s", request.url.path, exc)
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.") from exc
    except Exception as exc:
        logger.error("Unexpected error during JWT verification: %s", exc)
        raise HTTPException(status_code=401, detail="Authentication service error.")

    try:
        dept_store = get_department_store()
        return _build_user_from_payload(payload, department_store=dept_store)
    except Exception as exc:
        logger.error("Error building user from JWT payload: %s", exc)
        raise HTTPException(status_code=500, detail="Error resolving user profile.")


def get_optional_user(request: Request) -> Optional[CurrentUser]:
    """
    Like get_current_user but returns None instead of raising 401
    if no token is present. Used for endpoints that work with or without auth.
    """
    from .config import get_settings
    settings = get_settings()
    if not settings.auth_configured:
        if not settings.iris_demo_mode:
            return None
        return _DEMO_USER
    token = _extract_bearer_token(request)
    if not token:
        return None
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def require_role(*required_roles: Role):
    """
    Dependency factory that verifies the caller has one of the given roles.

    Usage::

        @router.post("/department/applications/{id}/assign")
        def assign(
            id: str,
            user: CurrentUser = Depends(require_role(Role.DEPARTMENT_MANAGER))
        ):
            ...

    This enforces authorization at the HTTP layer. Never rely only on
    frontend route hiding or navigation guards.
    """
    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(*required_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {[r.value for r in required_roles]}. "
                       f"Your role: {user.role.value}.",
            )
        return user
    return _check


def require_government(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """
    Dependency: caller must be any government role (OFFICER / MANAGER / ADMIN).
    Raises 403 if the caller is INDUSTRY_USER.
    """
    if not user.is_government():
        raise HTTPException(
            status_code=403,
            detail="Government portal access requires a DEPARTMENT_* role. "
                   "Industry users cannot access government operational data.",
        )
    return user


def require_department_admin(user: CurrentUser = Depends(require_role(Role.DEPARTMENT_ADMIN))) -> CurrentUser:
    """Dependency: caller must be DEPARTMENT_ADMIN."""
    return user
