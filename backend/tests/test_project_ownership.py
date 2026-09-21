"""
Tests for Industry Project Ownership and Tenant Isolation.

Verifies:
  1. Projects created by Industry User A are stamped with owner_id = User A's ID.
  2. Industry User A can list and view their own project.
  3. Industry User B CANNOT view User A's project in /projects listing.
  4. Industry User B requesting GET /projects/{user_a_proj_id} receives 404 Not Found.
  5. In production mode (IRIS_DEMO_MODE=false), legacy unowned projects (owner_id IS NULL)
     are NOT exposed to industry users, preventing data leaks.
  6. In demo mode (IRIS_DEMO_MODE=true), legacy unowned seed projects remain accessible.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.security import CurrentUser, Role, get_optional_user, get_current_user


def test_industry_user_creates_owned_project(client):
    """Creating a project stamps the caller's user_id as owner_id."""
    user_a = CurrentUser(
        user_id="ind-user-alpha",
        email="alpha@industry.com",
        role=Role.INDUSTRY_USER,
        department_id=None,
        name="Alpha Industrialist",
        is_demo=False,
    )

    app.dependency_overrides[get_optional_user] = lambda: user_a
    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        r = client.post(
            "/api/v1/projects",
            json={
                "id": "proj-alpha-1",
                "name": "Alpha Chemical Plant",
                "industry": "Chemicals",
            },
        )
        assert r.status_code == 201
        created = r.json()
        assert created["id"] == "proj-alpha-1"
        assert created["owner_id"] == "ind-user-alpha"
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_tenant_isolation_between_industry_users(monkeypatch):
    """User B cannot see User A's project in listing or direct lookup."""
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()

    user_a = CurrentUser(
        user_id="ind-user-alpha",
        email="alpha@industry.com",
        role=Role.INDUSTRY_USER,
        name="Alpha User",
        is_demo=False,
    )
    user_b = CurrentUser(
        user_id="ind-user-beta",
        email="beta@industry.com",
        role=Role.INDUSTRY_USER,
        name="Beta User",
        is_demo=False,
    )

    client = TestClient(app, raise_server_exceptions=False)
    try:
        # 1. User A creates project
        app.dependency_overrides[get_optional_user] = lambda: user_a
        app.dependency_overrides[get_current_user] = lambda: user_a
        r1 = client.post(
            "/api/v1/projects",
            json={
                "id": "proj-alpha-secret",
                "name": "Alpha Confidential Project",
                "industry": "Chemicals",
            },
        )
        assert r1.status_code == 201

        # User A can fetch it
        r_get_a = client.get("/api/v1/projects/proj-alpha-secret")
        assert r_get_a.status_code == 200

        # 2. Switch to User B
        app.dependency_overrides[get_optional_user] = lambda: user_b
        app.dependency_overrides[get_current_user] = lambda: user_b

        # User B listing must NOT contain User A's project
        r_list = client.get("/api/v1/projects")
        assert r_list.status_code == 200
        proj_ids = [p["id"] for p in r_list.json()]
        assert "proj-alpha-secret" not in proj_ids

        # User B direct GET must return 404 (not 403, to prevent enumeration)
        r_detail = client.get("/api/v1/projects/proj-alpha-secret")
        assert r_detail.status_code == 404
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        get_settings.cache_clear()


def test_production_unowned_projects_hidden_from_industry_users(monkeypatch):
    """
    In production mode (IRIS_DEMO_MODE=false), legacy unowned projects (owner_id IS NULL)
    must NOT be visible to authenticated Industry users.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()

    user = CurrentUser(
        user_id="ind-user-gamma",
        email="gamma@industry.com",
        role=Role.INDUSTRY_USER,
        name="Gamma User",
        is_demo=False,
    )

    client = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        # Listing should not include unowned demo projects like 'mahapharm'
        r = client.get("/api/v1/projects")
        assert r.status_code == 200
        proj_ids = [p["id"] for p in r.json()]
        assert "mahapharm" not in proj_ids

        # Direct GET to unowned project returns 404 in production
        r_detail = client.get("/api/v1/projects/mahapharm")
        assert r_detail.status_code == 404
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        get_settings.cache_clear()


def test_demo_mode_allows_unowned_projects(monkeypatch):
    """
    In demo mode (IRIS_DEMO_MODE=true), legacy unowned demo projects (mahapharm)
    remain accessible.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "true")
    get_settings.cache_clear()

    client = TestClient(app)
    try:
        r = client.get("/api/v1/projects")
        assert r.status_code == 200
        proj_ids = [p["id"] for p in r.json()]
        assert "mahapharm" in proj_ids

        r_detail = client.get("/api/v1/projects/mahapharm")
        assert r_detail.status_code == 200
        assert r_detail.json()["id"] == "mahapharm"
    finally:
        get_settings.cache_clear()
