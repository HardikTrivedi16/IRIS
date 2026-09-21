"""
Regression tests: POST /api/v1/evaluate and /evaluate/all must enforce the
same project authorization as every /projects/{id}/* endpoint.

Before the fix both endpoints accepted unauthenticated requests for ANY
project_id, loaded that project's stored Project Facts, and echoed them back
in the Decision's condition tree (actual_project_value).
"""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.security import CurrentUser, Role, get_current_user, get_optional_user

SECRET_FACT = "project.likely_to_discharge_sewage_or_trade_effluent"


def _user(uid: str) -> CurrentUser:
    return CurrentUser(
        user_id=uid,
        email=f"{uid}@industry.test",
        role=Role.INDUSTRY_USER,
        name=uid,
        is_demo=False,
    )


def _as(user):
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user


def _clear():
    app.dependency_overrides.pop(get_optional_user, None)
    app.dependency_overrides.pop(get_current_user, None)


def _eval(c, project_id, **extra):
    return c.post(
        "/api/v1/evaluate",
        json={
            "project_id": project_id,
            "requirement_id": "REQ-0001",
            "evaluation_mode": "NON_PRODUCTION",
            "persist": False,
            **extra,
        },
    )


def _eval_all(c, project_id):
    return c.post(
        "/api/v1/evaluate/all",
        json={"project_id": project_id, "evaluation_mode": "NON_PRODUCTION", "persist": False},
    )


@pytest.fixture()
def prod_client(monkeypatch):
    """Fail-closed posture: demo mode OFF, Supabase unset (in-memory store)."""
    from app.store import get_store
    from app.engine_service import get_dataset, get_engine

    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()
    get_store.cache_clear()
    get_dataset.cache_clear()
    get_engine.cache_clear()
    c = TestClient(app, raise_server_exceptions=False)

    # Owner creates a project with a stored fact that must stay private.
    _as(_user("owner-a"))
    assert c.post(
        "/api/v1/projects",
        json={"id": "proj-owned-a", "name": "Owner A Plant", "industry": "food"},
    ).status_code == 201
    assert c.post(
        "/api/v1/projects/proj-owned-a/facts", json={"facts": {SECRET_FACT: True}}
    ).status_code == 200
    _clear()
    try:
        yield c
    finally:
        _clear()
        get_settings.cache_clear()
        get_store.cache_clear()


# --- unauthenticated --------------------------------------------------------

def test_unauthenticated_evaluate_fails_closed(prod_client):
    r = _eval(prod_client, "proj-owned-a")
    assert r.status_code == 401
    assert SECRET_FACT not in r.text


def test_unauthenticated_evaluate_all_fails_closed(prod_client):
    r = _eval_all(prod_client, "proj-owned-a")
    assert r.status_code == 401
    assert SECRET_FACT not in r.text


# --- owner ------------------------------------------------------------------

def test_owner_can_evaluate_with_stored_facts(prod_client):
    _as(_user("owner-a"))
    r = _eval(prod_client, "proj-owned-a")
    assert r.status_code == 200
    tree = r.json()["decision"]["explanation"]["condition_evaluation_tree"]
    assert tree["actual_project_value"] is True  # the owner's own stored fact


def test_owner_can_evaluate_all(prod_client):
    _as(_user("owner-a"))
    r = _eval_all(prod_client, "proj-owned-a")
    assert r.status_code == 200
    assert len(r.json()["decisions"]) >= 1


# --- cross-user ---------------------------------------------------------------

def test_cross_user_evaluate_is_404_and_leaks_nothing(prod_client):
    _as(_user("intruder-b"))
    r = _eval(prod_client, "proj-owned-a")
    assert r.status_code == 404
    assert SECRET_FACT not in r.text
    # Same generic body a nonexistent project gets — no existence oracle.
    assert r.json() == {"detail": "Project proj-owned-a not found"}


def test_cross_user_evaluate_all_is_404(prod_client):
    _as(_user("intruder-b"))
    r = _eval_all(prod_client, "proj-owned-a")
    assert r.status_code == 404
    assert SECRET_FACT not in r.text


def test_cross_user_cannot_probe_with_body_facts(prod_client):
    """Supplying ad-hoc facts must not bypass the ownership check."""
    _as(_user("intruder-b"))
    r = _eval(prod_client, "proj-owned-a", facts={SECRET_FACT: False})
    assert r.status_code == 404


# --- nonexistent ----------------------------------------------------------------

def test_nonexistent_project_evaluate_is_404(prod_client):
    _as(_user("owner-a"))
    assert _eval(prod_client, "does-not-exist").status_code == 404


def test_nonexistent_project_evaluate_all_is_404(prod_client):
    _as(_user("owner-a"))
    assert _eval_all(prod_client, "does-not-exist").status_code == 404


# --- demo mode preserved ------------------------------------------------------

def test_demo_mode_still_evaluates_seeded_project(client):
    """Default test session runs IRIS_DEMO_MODE=true: behaviour unchanged."""
    r = _eval(client, "mahapharm")
    assert r.status_code == 200
    assert _eval_all(client, "mahapharm").status_code == 200


def test_demo_mode_nonexistent_project_is_404(client):
    assert _eval(client, "no-such-project").status_code == 404
