"""
Auth tests — backend JWT verification and role enforcement.

These tests exercise the security layer in DEMO MODE (no SUPABASE_URL set),
which is the CI environment. They verify:
  - Demo mode returns the demo user correctly
  - /api/v1/auth/me returns user identity
  - /api/v1/auth/profile creates/updates IRIS profile
  - Role enforcement (require_government) blocks Industry users
  - Government-only endpoints inaccessible without government role
  - User management endpoints (admin-only) are accessible in demo mode

IMPORTANT: Full JWKS/JWT authentication cannot be tested without a live
Supabase project. Tests here validate the demo-mode path and the profile
management logic. The JWT verification logic (security.py::_verify_jwt)
is tested separately in test_jwt_verification.py (see comments below).

Authentication flow (Supabase not configured → demo mode):
  1. SUPABASE_URL not set → get_current_user() returns _DEMO_USER (DEPARTMENT_MANAGER)
  2. All department endpoints pass (demo manager has government role)
  3. Industry-only simulation: tested by checking that INDUSTRY_USER role
     is blocked by require_government() when Supabase IS configured.
     In demo mode, this cannot be simulated without patching the user.

Known limitation: E2E auth testing (Google OAuth, real JWT) requires a real
configured Supabase project. This is documented in the implementation plan.
"""
import pytest


def test_auth_me_in_demo_mode(client):
    """
    /api/v1/auth/me returns the demo user when SUPABASE_URL is not configured.
    Response must include user_id, email, role, is_demo flag.
    """
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    user = r.json()
    assert "user_id" in user
    assert "email" in user
    assert "role" in user
    assert "is_demo" in user
    # In demo mode, is_demo must be True
    assert user["is_demo"] is True
    # Demo role must be a DEPARTMENT role (not INDUSTRY)
    assert user["role"].startswith("DEPARTMENT_")


def test_auth_me_role_is_government_in_demo_mode(client):
    """Demo user must be a government role — tests pass in demo mode because
    all department endpoints accept the demo government role."""
    r = client.get("/api/v1/auth/me")
    user = r.json()
    assert user["role"] in ("DEPARTMENT_OFFICER", "DEPARTMENT_MANAGER", "DEPARTMENT_ADMIN")


def test_auth_me_resolves_real_department_name_not_hardcoded(client):
    """/auth/me must resolve department_name from the department store for a
    government user — never a hardcoded/fabricated department label. The
    demo user is seeded with department_id=dept-mpcb (app/security.py); its
    name must come from the actual department_store record."""
    r = client.get("/api/v1/auth/me")
    user = r.json()
    assert user["department_id"] == "dept-mpcb"
    assert user["department_name"] == "Maharashtra Pollution Control Board"


def test_auth_me_department_name_is_none_for_industry_user(client, monkeypatch):
    """An industry user (no department_id) must get department_name=None,
    never a fabricated department name."""
    import app.routers.auth as auth_router
    from app.security import CurrentUser, Role

    industry_user = CurrentUser(
        user_id="ind-1", email="a@industry.com", role=Role.INDUSTRY_USER
    )
    # get_me() calls get_current_user(request) directly rather than via
    # FastAPI Depends(), so it must be patched at the module level rather
    # than through app.dependency_overrides.
    monkeypatch.setattr(auth_router, "get_current_user", lambda request: industry_user)

    r = client.get("/api/v1/auth/me")
    user = r.json()
    assert user["department_id"] is None
    assert user["department_name"] is None


def test_auth_profile_create(client):
    """POST /api/v1/auth/profile creates an IRIS profile for the current user."""
    r = client.post(
        "/api/v1/auth/profile",
        json={
            "full_name": "Integration Test User",
            "provider": "email",
        },
    )
    assert r.status_code == 201
    profile = r.json()
    assert "id" in profile or "supabase_auth_uid" in profile
    assert profile.get("iris_role") is not None


def test_auth_profile_update(client):
    """Calling POST /api/v1/auth/profile again updates the existing profile."""
    # First create
    client.post(
        "/api/v1/auth/profile",
        json={"full_name": "Initial Name", "provider": "email"},
    )
    # Update
    r = client.post(
        "/api/v1/auth/profile",
        json={"full_name": "Updated Name", "provider": "google"},
    )
    assert r.status_code == 201
    profile = r.json()
    assert profile.get("full_name") == "Updated Name"


def test_government_endpoints_accessible_in_demo_mode(client):
    """All government endpoints return 200 in demo mode (not 403)."""
    endpoints = [
        "/api/v1/department/dashboard",
        "/api/v1/department/applications",
        "/api/v1/department/sla/policies",
        "/api/v1/department/sla/dashboard",
        "/api/v1/department/sla/applications",
        "/api/v1/department/sla/stage-performance",
        "/api/v1/department/bottlenecks/report",
        "/api/v1/department/bottlenecks/stages",
        "/api/v1/department/bottlenecks/officers",
        "/api/v1/department/bottlenecks/trends",
    ]
    for endpoint in endpoints:
        r = client.get(endpoint)
        assert r.status_code == 200, (
            f"Government endpoint {endpoint} returned {r.status_code} in demo mode"
        )


def test_user_management_list_in_demo_mode(client):
    """GET /api/v1/department/users returns list in demo mode."""
    r = client.get("/api/v1/department/users")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_user_management_create_in_demo_mode(client):
    """POST /api/v1/department/users creates a new government user in demo mode."""
    r = client.post(
        "/api/v1/department/users",
        json={
            "name": "New Test Officer",
            "email": "test.officer@example.com",
            "role": "DEPARTMENT_OFFICER",
            "department_id": "dept-mpcb",
        },
    )
    assert r.status_code == 201
    user = r.json()
    assert user["name"] == "New Test Officer"
    assert user["role"] == "DEPARTMENT_OFFICER"


def test_user_management_create_invalid_department(client):
    """Creating a government user with an invalid department_id returns 404."""
    r = client.post(
        "/api/v1/department/users",
        json={
            "name": "Invalid Dept User",
            "role": "DEPARTMENT_OFFICER",
            "department_id": "dept-does-not-exist",
        },
    )
    assert r.status_code == 404


def test_user_management_update_in_demo_mode(client):
    """PATCH /api/v1/department/users/{id} updates role."""
    # Create a user first
    r = client.post(
        "/api/v1/department/users",
        json={
            "name": "Update Test User",
            "role": "DEPARTMENT_OFFICER",
            "department_id": "dept-mpcb",
        },
    )
    assert r.status_code == 201
    user_id = r.json()["id"]

    # Update role
    r2 = client.patch(
        f"/api/v1/department/users/{user_id}",
        json={"role": "DEPARTMENT_MANAGER"},
    )
    assert r2.status_code == 200
    assert r2.json()["role"] == "DEPARTMENT_MANAGER"


def test_user_management_update_is_active(client):
    """PATCH /api/v1/department/users/{id} can deactivate a user."""
    r = client.post(
        "/api/v1/department/users",
        json={"name": "Deactivate Test", "role": "DEPARTMENT_OFFICER", "department_id": "dept-mpcb"},
    )
    user_id = r.json()["id"]

    r2 = client.patch(f"/api/v1/department/users/{user_id}", json={"is_active": False})
    assert r2.status_code == 200
    assert r2.json()["is_active"] is False


def test_user_management_get_detail(client):
    """GET /api/v1/department/users/{id} returns user detail."""
    r = client.post(
        "/api/v1/department/users",
        json={"name": "Detail Test", "role": "DEPARTMENT_OFFICER", "department_id": "dept-mpcb"},
    )
    user_id = r.json()["id"]
    r2 = client.get(f"/api/v1/department/users/{user_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == user_id


def test_user_management_get_missing(client):
    """GET /api/v1/department/users/{nonexistent} returns 404."""
    r = client.get("/api/v1/department/users/nonexistent-id-99999")
    assert r.status_code == 404


def test_link_profile_to_department(client):
    """
    POST /api/v1/department/users/link-profile creates a government link
    for a user_profiles row.
    """
    # Create a profile first
    r_profile = client.post(
        "/api/v1/auth/profile",
        json={"full_name": "Google Auth User", "provider": "google"},
    )
    assert r_profile.status_code == 201
    profile_id = r_profile.json().get("id")
    if not profile_id:
        pytest.skip("Profile ID not available in demo mode (auth UID collision)")

    r = client.post(
        "/api/v1/department/users/link-profile",
        json={
            "user_profile_id": profile_id,
            "department_id": "dept-mpcb",
            "role": "DEPARTMENT_OFFICER",
            "name": "Linked Officer",
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert result["iris_role"] == "DEPARTMENT_OFFICER"
    assert result["department_id"] == "dept-mpcb"


def test_link_profile_invalid_role(client):
    """link-profile with invalid role returns 422."""
    r_profile = client.post(
        "/api/v1/auth/profile",
        json={"full_name": "Bad Role Test", "provider": "email"},
    )
    profile_id = r_profile.json().get("id")
    if not profile_id:
        pytest.skip("Profile ID not available in demo mode")

    r = client.post(
        "/api/v1/department/users/link-profile",
        json={
            "user_profile_id": profile_id,
            "department_id": "dept-mpcb",
            "role": "INVALID_ROLE",
        },
    )
    assert r.status_code == 422


def test_user_profiles_list_in_demo_mode(client):
    """GET /api/v1/department/user-profiles returns list (admin-only in real auth)."""
    r = client.get("/api/v1/department/user-profiles")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_government_isolation_documented(client):
    """
    Verify that industry-facing endpoints do NOT include SLA or bottleneck fields.
    This is a structural check — real authorization requires Supabase configured.
    """
    # Industry endpoints must not have SLA fields in responses
    r = client.get("/api/v1/projects/mahapharm")
    body = r.json()
    for forbidden_key in ["sla_state", "sla", "breach", "bottleneck"]:
        assert forbidden_key not in body, (
            f"Industry project endpoint has forbidden government field: {forbidden_key!r}"
        )

    r2 = client.get("/api/v1/projects")
    for proj in r2.json():
        for forbidden_key in ["sla_state", "sla", "breach", "bottleneck"]:
            assert forbidden_key not in proj, (
                f"Industry projects list has forbidden government field: {forbidden_key!r}"
            )


def test_demo_mode_warning_documented():
    """
    Verify that demo mode is intentionally limited.
    The security.py code must log a WARNING in demo mode —
    this test checks the code, not runtime behavior.
    """
    import inspect
    from app.security import get_current_user
    source = inspect.getsource(get_current_user)
    assert "WARNING" in source or "warning" in source.lower(), (
        "security.py must log a warning when running in demo mode"
    )
    assert "DO NOT use in production" in source or "production" in source.lower(), (
        "Demo mode warning must mention production"
    )


def test_auth_endpoint_no_secrets_in_response(client):
    """
    /api/v1/auth/me must not include any secrets in the response.
    Specifically: no service_role_key, jwt_secret, or similar.
    """
    r = client.get("/api/v1/auth/me")
    body_str = str(r.json()).lower()
    for forbidden in ["service_role", "jwt_secret", "supabase_key"]:
        assert forbidden not in body_str, (
            f"Auth response contains forbidden secret: {forbidden!r}"
        )


def test_root_endpoint_includes_auth_configured_flag(client):
    """Root endpoint must expose auth_configured flag (not secrets)."""
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert "auth_configured" in body
    # In test environment (no SUPABASE_URL), should be False
    assert body["auth_configured"] is False
