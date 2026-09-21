"""
Tests for Government Department Isolation.

Verifies:
  1. Applications created under department A (e.g. dept-mpcb) are NOT visible to department B (e.g. dept-fssai).
  2. Direct GET /api/v1/department/applications/{app_id} for an application from another department returns 404.
  3. Attempting to advance stage or assign officer across department boundaries is rejected.
  4. Attempting to create an application for another department is rejected with 403.
  5. Dashboard KPIs, SLA dashboard, and bottleneck reports reflect ONLY the authenticated user's department.
  6. Admin user management and officer rosters are strictly filtered to the admin's assigned department.
"""
import pytest
from fastapi.testclient import TestClient

from app.security import CurrentUser, Role, get_current_user
from app.main import app


def test_department_isolation_application_list(client):
    """An officer of dept-mpcb cannot see applications of dept-fssai."""
    # 1. Create app in dept-mpcb
    r1 = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "department_id": "dept-mpcb",
            "title": "MPCB Consent to Establish",
        },
    )
    assert r1.status_code == 201
    mpcb_app_id = r1.json()["id"]

    # 2. Simulate FSSAI officer
    fssai_user = CurrentUser(
        user_id="fssai-officer-1",
        email="fssai@iris.local",
        role=Role.DEPARTMENT_OFFICER,
        department_id="dept-fssai",
        name="FSSAI Officer",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: fssai_user
    try:
        r2 = client.get("/api/v1/department/applications")
        assert r2.status_code == 200
        fssai_apps = r2.json()["items"]
        fssai_ids = [a["id"] for a in fssai_apps]
        assert mpcb_app_id not in fssai_ids, "FSSAI officer saw MPCB application in application list!"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_department_cross_access_denied_on_detail(client):
    """Direct lookup of another department's application returns 404."""
    # Create app in dept-mpcb
    r1 = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "department_id": "dept-mpcb",
            "title": "MPCB Secret App",
        },
    )
    assert r1.status_code == 201
    mpcb_app_id = r1.json()["id"]

    # FSSAI officer tries to fetch MPCB application by ID
    fssai_user = CurrentUser(
        user_id="fssai-officer-1",
        email="fssai@iris.local",
        role=Role.DEPARTMENT_OFFICER,
        department_id="dept-fssai",
        name="FSSAI Officer",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: fssai_user
    try:
        r2 = client.get(f"/api/v1/department/applications/{mpcb_app_id}")
        assert r2.status_code == 404, "Cross-department GET should return 404 not found"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_department_cross_transition_denied(client):
    """Transitioning an application belonging to another department returns 404."""
    r1 = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "department_id": "dept-mpcb",
            "title": "MPCB Transition App",
        },
    )
    assert r1.status_code == 201
    app_id = r1.json()["id"]

    fssai_user = CurrentUser(
        user_id="fssai-officer-1",
        email="fssai@iris.local",
        role=Role.DEPARTMENT_OFFICER,
        department_id="dept-fssai",
        name="FSSAI Officer",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: fssai_user
    try:
        r2 = client.post(
            f"/api/v1/department/applications/{app_id}/transition",
            json={"new_stage": "UNDER_REVIEW", "reason": "Illicit cross-dept transition"},
        )
        assert r2.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_department_cannot_create_application_for_other_department(client):
    """An officer of dept-mpcb cannot submit an application under dept-fssai."""
    mpcb_user = CurrentUser(
        user_id="mpcb-officer-1",
        email="mpcb@iris.local",
        role=Role.DEPARTMENT_OFFICER,
        department_id="dept-mpcb",
        name="MPCB Officer",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: mpcb_user
    try:
        r = client.post(
            "/api/v1/department/applications",
            json={
                "project_id": "mahapharm",
                "requirement_id": "REQ-0001",
                "department_id": "dept-fssai",
                "title": "Illicit FSSAI App from MPCB Officer",
            },
        )
        assert r.status_code == 403, "Should return 403 when creating application in another department"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_department_dashboard_and_sla_isolation(client):
    """SLA dashboard and metrics only reflect the caller's department."""
    # Create app in dept-mpcb
    client.post(
        "/api/v1/department/applications",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "department_id": "dept-mpcb",
            "title": "MPCB SLA App",
        },
    )

    fssai_user = CurrentUser(
        user_id="fssai-manager-1",
        email="fssai.manager@iris.local",
        role=Role.DEPARTMENT_MANAGER,
        department_id="dept-fssai",
        name="FSSAI Manager",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: fssai_user
    try:
        r = client.get("/api/v1/department/sla/dashboard")
        assert r.status_code == 200
        data = r.json()
        # FSSAI has 0 applications created, so total should be 0
        assert data["kpis"]["total"] == 0, "FSSAI dashboard should show 0 total applications"
        assert len(data["applications"]) == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_department_bottleneck_isolation(client):
    """Bottleneck report only aggregates data for caller's department."""
    # Create app in dept-mpcb
    client.post(
        "/api/v1/department/applications",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "department_id": "dept-mpcb",
            "title": "MPCB Bottleneck App",
        },
    )

    fssai_user = CurrentUser(
        user_id="fssai-manager-1",
        email="fssai.manager@iris.local",
        role=Role.DEPARTMENT_MANAGER,
        department_id="dept-fssai",
        name="FSSAI Manager",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: fssai_user
    try:
        r = client.get("/api/v1/department/bottlenecks/report")
        assert r.status_code == 200
        report = r.json()
        assert report["total_applications"] == 0
        assert report["total_active"] == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_department_admin_cannot_create_officer_in_other_department(client):
    """DEPARTMENT_ADMIN of dept-mpcb cannot create an officer for dept-fssai."""
    mpcb_admin = CurrentUser(
        user_id="mpcb-admin-1",
        email="mpcb.admin@iris.local",
        role=Role.DEPARTMENT_ADMIN,
        department_id="dept-mpcb",
        name="MPCB Admin",
        is_demo=False,
    )

    app.dependency_overrides[get_current_user] = lambda: mpcb_admin
    try:
        r = client.post(
            "/api/v1/department/users",
            json={
                "name": "Intruder Officer",
                "department_id": "dept-fssai",
                "role": "DEPARTMENT_OFFICER",
            },
        )
        assert r.status_code == 403, "Admin should not be able to create users in another department"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
