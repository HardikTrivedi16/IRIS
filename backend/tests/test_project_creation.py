"""
P0-A — New Project / Add Factory (backend contract).

Covers the intake validation and the duplicate-id guard added in this pass,
plus the end-to-end create -> facts -> evaluate flow the frontend wizard
drives. Ownership is exercised in the fail-closed (non-demo) posture.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.security import CurrentUser, Role, get_current_user, get_optional_user


def _user(uid: str) -> CurrentUser:
    return CurrentUser(user_id=uid, email=f"{uid}@x.test", role=Role.INDUSTRY_USER,
                       name=uid, is_demo=False)


def _as(user):
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture()
def prod(monkeypatch):
    from app.store import get_store
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()
    get_store.cache_clear()
    c = TestClient(app, raise_server_exceptions=False)
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        get_settings.cache_clear()
        get_store.cache_clear()


BASIC = {
    "name": "Pune Food Processing Unit",
    "industry": "food",
    "activity": "Fruit pulp processing",
    "location": "Pune, Maharashtra",
    "stage": "pre-establishment",
    "scale": "small",
    "workers": 40,
}


# --- create / retrieve / list -------------------------------------------------

def test_create_retrieve_and_list(prod):
    _as(_user("owner-a"))
    r = prod.post("/api/v1/projects", json=BASIC)
    assert r.status_code == 201
    created = r.json()
    pid = created["id"]
    assert len(pid) >= 8                      # server-generated, no hardcoded id
    assert created["owner_id"] == "owner-a"

    got = prod.get(f"/api/v1/projects/{pid}")
    assert got.status_code == 200 and got.json()["name"] == BASIC["name"]
    assert pid in {p["id"] for p in prod.get("/api/v1/projects").json()}


def test_two_creates_get_distinct_ids(prod):
    _as(_user("owner-a"))
    a = prod.post("/api/v1/projects", json=BASIC).json()["id"]
    b = prod.post("/api/v1/projects", json=BASIC).json()["id"]
    assert a != b


def test_unauthenticated_create_fails_closed(prod):
    assert prod.post("/api/v1/projects", json=BASIC).status_code == 401


def test_other_user_cannot_see_new_project(prod):
    _as(_user("owner-a"))
    pid = prod.post("/api/v1/projects", json=BASIC).json()["id"]
    _as(_user("user-b"))
    assert prod.get(f"/api/v1/projects/{pid}").status_code == 404
    assert pid not in {p["id"] for p in prod.get("/api/v1/projects").json()}


# --- duplicate handling -----------------------------------------------------------

def test_duplicate_id_rejected_and_original_untouched(prod):
    _as(_user("owner-a"))
    assert prod.post("/api/v1/projects", json={**BASIC, "id": "dup-proj"}).status_code == 201
    r = prod.post("/api/v1/projects", json={**BASIC, "id": "dup-proj", "name": "Overwrite"})
    assert r.status_code == 409
    assert prod.get("/api/v1/projects/dup-proj").json()["name"] == BASIC["name"]


def test_cross_user_duplicate_cannot_take_over_project(prod):
    """Before the fix both stores upserted on id, so user B could overwrite
    user A's project and re-stamp owner_id to themselves."""
    _as(_user("owner-a"))
    prod.post("/api/v1/projects", json={**BASIC, "id": "victim-proj"})
    _as(_user("attacker-b"))
    r = prod.post("/api/v1/projects", json={**BASIC, "id": "victim-proj", "name": "Pwned"})
    assert r.status_code == 409
    assert "owner" not in r.text.lower()
    _as(_user("owner-a"))
    proj = prod.get("/api/v1/projects/victim-proj").json()
    assert proj["owner_id"] == "owner-a" and proj["name"] == BASIC["name"]


# --- validation -------------------------------------------------------------------

@pytest.mark.parametrize(
    "patch",
    [
        {"name": ""},
        {"name": "   "},
        {"industry": ""},
        {"workers": -1},
        {"id": "has spaces"},
        {"id": "../etc"},
        {"name": "x" * 201},
    ],
)
def test_invalid_intake_rejected(prod, patch):
    _as(_user("owner-a"))
    assert prod.post("/api/v1/projects", json={**BASIC, **patch}).status_code == 422


def test_missing_required_fields_rejected(prod):
    _as(_user("owner-a"))
    assert prod.post("/api/v1/projects", json={"industry": "food"}).status_code == 422
    assert prod.post("/api/v1/projects", json={"name": "X"}).status_code == 422


def test_name_is_trimmed(prod):
    _as(_user("owner-a"))
    assert prod.post("/api/v1/projects", json={**BASIC, "name": "  Trim Me  "}).json()["name"] == "Trim Me"


# --- project facts ----------------------------------------------------------------

def test_facts_endpoint_rejects_wrong_type_for_engine_fact(prod):
    _as(_user("owner-a"))
    pid = prod.post("/api/v1/projects", json=BASIC).json()["id"]
    r = prod.post(f"/api/v1/projects/{pid}/facts",
                  json={"facts": {"project.dairy_liquid_milk_capacity": "a lot"}})
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0]["code"] == "INVALID_VALUE_TYPE"
    assert prod.get(f"/api/v1/projects/{pid}/facts").json()["facts"] == {}


def test_facts_endpoint_still_accepts_document_facts_and_nulls(prod):
    _as(_user("owner-a"))
    pid = prod.post("/api/v1/projects", json=BASIC).json()["id"]
    r = prod.post(f"/api/v1/projects/{pid}/facts", json={"facts": {
        "document.business_name": "Anything",       # not an engine fact: untouched
        "project.industry": "FOOD",
        "project.plant_located_in_air_pollution_control_area": None,  # explicit unknown
    }})
    assert r.status_code == 200


def test_new_project_evaluation_requires_information_not_guessed(prod):
    """End to end: a new project with only some facts must report the
    missing ones, never guess them."""
    _as(_user("owner-a"))
    pid = prod.post("/api/v1/projects", json=BASIC).json()["id"]
    prod.post(f"/api/v1/projects/{pid}/facts", json={"facts": {"project.industry": "FOOD"}})

    r = prod.post("/api/v1/evaluate/all",
                  json={"project_id": pid, "evaluation_mode": "NON_PRODUCTION", "persist": False})
    assert r.status_code == 200
    by_req = {d["requirement_id"]: d for d in r.json()["decisions"]}
    assert by_req["REQ-0001"]["final_state"] == "REQUIRES_INFORMATION"
    assert by_req["REQ-0001"]["missing_project_fact_keys"] == [
        "project.likely_to_discharge_sewage_or_trade_effluent"]
    assert by_req["REQ-0004"]["final_state"] == "REQUIRES_INFORMATION"  # dairy capacity unknown

    prod_mode = prod.post("/api/v1/evaluate/all", json={"project_id": pid, "persist": False})
    assert {d["final_state"] for d in prod_mode.json()["decisions"]} == {"BLOCKED_DRAFT_NOT_PRODUCTION"}
