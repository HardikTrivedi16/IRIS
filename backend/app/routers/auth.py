"""
Auth router — user profile and identity management.

Endpoints:
  GET  /api/v1/auth/me        — return current user profile (requires valid JWT)
  POST /api/v1/auth/profile   — create/update IRIS profile on first login

Security notes:
  - These endpoints require a valid Supabase JWT (from Authorization: Bearer header).
  - No Supabase service-role key or JWT secret is ever returned to the client.
  - Profile linkage to department_users (government access) happens via
    /api/v1/department/users (admin-only), NOT automatically here.
  - Google OAuth identity → IRIS profile → admin assigns department/role.
    Authenticating with Google does NOT automatically grant government access.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..security import get_current_user, CurrentUser
from ..store.department_store import get_department_store

logger = logging.getLogger("iris.api.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me")
def get_me(request: Request) -> dict:
    """
    Return the current authenticated user's IRIS profile.

    Requires: Authorization: Bearer <supabase_jwt>

    Response includes:
      - user_id: Supabase auth UID (sub claim)
      - email
      - role: IRIS role (INDUSTRY_USER by default until admin assigns a government role)
      - department_id: set for government users, null for industry users
      - department_name: human-readable department name (government users only;
        looked up from the department store, never hardcoded/fabricated)
      - name: display name
      - is_demo: true in demo mode (no Supabase configured)

    This endpoint is safe for the frontend to call to determine where to
    redirect after login (industry portal vs government portal).
    """
    user: CurrentUser = get_current_user(request)
    payload = user.to_dict()
    payload["department_name"] = None
    if user.department_id:
        try:
            dept = get_department_store().get_department(user.department_id)
            payload["department_name"] = dept.get("name") if dept else None
        except Exception:
            logger.warning("Could not resolve department name for %s", user.department_id)
    return payload


@router.post("/profile", status_code=201)
def create_or_update_profile(request: Request, body: dict) -> dict:
    """
    Create or update the IRIS user profile for the authenticated user.

    Call this after first Supabase Auth login (email, Google OAuth, etc.)
    to ensure the user has an IRIS profile record.

    Body fields (all optional except the token must be valid):
      - full_name: str
      - avatar_url: str
      - provider: str  ('email', 'google', etc.)

    The IRIS role defaults to INDUSTRY_USER. Government role assignment
    requires an explicit admin action via /api/v1/department/users/{id}.

    Returns the updated/created user profile.
    """
    user: CurrentUser = get_current_user(request)
    ds = get_department_store()

    profile_data = {
        "supabase_auth_uid": user.user_id,
        "email": user.email,
        "full_name": body.get("full_name") or user.name,
        "avatar_url": body.get("avatar_url"),
        "provider": body.get("provider", "email"),
    }
    profile = ds.create_or_update_user_profile(profile_data)

    # Enrich with current IRIS role from the verified JWT lookup
    profile["iris_role"] = user.role.value
    profile["department_id"] = user.department_id

    return profile
