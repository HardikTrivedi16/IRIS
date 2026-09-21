"""P1-H — grievance preparation / tracking / hand-off."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.security import CurrentUser, Role, get_current_user, get_optional_user

GOOD = {
    "category": "PROCESSING_DELAY",
    "description": "Application has been under review well beyond the SLA window shown.",
    "acknowledge_not_statutory": True,
}


def _make_app(client, project_id="freshbite"):
    r = client.post("/api/v1/department/applications", json={
        "project_id": project_id, "requirement_id": "REQ-0001", "department_id": "dept-mpcb",
        "title": "Consent to Establish — Water Act", "sla_policy_id": "sla-standard-30d"})
    assert r.status_code == 201, r.text
    return r.json()


def _raise(client, app_id, project_id="freshbite", **over):
    return client.post(f"/api/v1/projects/{project_id}/grievances",
                       json={**GOOD, "application_id": app_id, **over})


# --- demo-mode happy path ----------------------------------------------------------

def test_project_applications_visible_to_applicant_without_officer_details(client):
    a = _make_app(client)
    [row] = client.get("/api/v1/projects/freshbite/applications").json()
    assert row["id"] == a["id"] and row["current_stage"]
    assert "sla" in row and "state" in row["sla"]
    assert "assigned_officer_id" not in row and "assigned_officer_name" not in row


def test_create_attaches_server_side_context_and_history(client):
    a = _make_app(client)
    r = _raise(client, a["id"])
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["status"] == "OPEN" and g["grievance_number"].startswith("GRV-")
    ctx = g["context_snapshot"]
    assert ctx["application_number"] == a["application_id"]
    assert ctx["current_stage"] == a["current_stage"]
    assert ctx["sla"]["state"] is not None  # computed by the department store
    assert [h["to_status"] for h in g["history"]] == ["OPEN"]
    assert "not a statutory" in g["disclaimer"]


def test_never_filed_without_explicit_acknowledgement(client):
    a = _make_app(client)
    assert _raise(client, a["id"], acknowledge_not_statutory=False).status_code == 422
    assert client.get("/api/v1/projects/freshbite/grievances").json() == []


def test_validation(client):
    a = _make_app(client)
    assert _raise(client, a["id"], description="short").status_code == 422
    assert _raise(client, a["id"], category="STATUTORY_APPEAL").status_code == 422


def test_application_must_belong_to_project(client):
    a = _make_app(client, project_id="mahapharm")
    assert _raise(client, a["id"], project_id="freshbite").status_code == 404
    assert _raise(client, "no-such-app").status_code == 404


def test_government_full_workflow_preserves_history(client):
    a = _make_app(client)
    gid = _raise(client, a["id"]).json()["id"]

    listing = client.get("/api/v1/department/grievances").json()
    assert [g["id"] for g in listing] == [gid]

    r = client.post(f"/api/v1/department/grievances/{gid}/assign", json={"officer_id": "du-demo-officer"})
    assert r.status_code == 200 and r.json()["status"] == "ASSIGNED"
    assert r.json()["assigned_officer_name"] == "Priya Sharma"

    r = client.post(f"/api/v1/department/grievances/{gid}/transition", json={"to_status": "UNDER_REVIEW"})
    assert r.json()["status"] == "UNDER_REVIEW"

    # Resolution requires a note.
    bad = client.post(f"/api/v1/department/grievances/{gid}/transition", json={"to_status": "RESOLVED"})
    assert bad.status_code == 422
    r = client.post(f"/api/v1/department/grievances/{gid}/transition",
                    json={"to_status": "RESOLVED", "note": "Query clarified and review resumed."})
    assert r.json()["status"] == "RESOLVED"
    assert r.json()["resolution_note"] == "Query clarified and review resumed."

    r = client.post(f"/api/v1/department/grievances/{gid}/transition", json={"to_status": "CLOSED"})
    g = r.json()
    assert g["status"] == "CLOSED"
    assert [h["to_status"] for h in g["history"]] == ["OPEN", "ASSIGNED", "UNDER_REVIEW", "RESOLVED", "CLOSED"]
    # The applicant sees the same history.
    mine = client.get(f"/api/v1/projects/freshbite/grievances/{gid}").json()
    assert len(mine["history"]) == 5


def test_invalid_transitions_rejected(client):
    a = _make_app(client)
    gid = _raise(client, a["id"]).json()["id"]
    r = client.post(f"/api/v1/department/grievances/{gid}/transition", json={"to_status": "CLOSED"})
    assert r.status_code == 422
    assert client.post(f"/api/v1/department/grievances/{gid}/assign",
                       json={"officer_id": "not-an-officer"}).status_code == 422


def test_context_snapshot_is_not_client_supplied(client):
    a = _make_app(client)
    r = _raise(client, a["id"], context_snapshot={"sla": {"state": "BREACHED"}})
    assert r.status_code == 201
    # A freshly created application cannot be BREACHED: the client value was ignored.
    assert r.json()["context_snapshot"]["sla"]["state"] != "BREACHED"
    assert r.json()["context_snapshot"]["application_number"] == a["application_id"]


# --- RBAC (fail-closed posture) -------------------------------------------------------

def _user(uid, role, dept=None):
    return CurrentUser(user_id=uid, email=f"{uid}@x", role=role, department_id=dept, name=uid, is_demo=False)


@pytest.fixture()
def prod(monkeypatch):
    """Fail-closed posture (demo mode OFF). The department and grievance stores
    refuse to start without Supabase in that posture, so in-memory instances
    are injected into the routers; the routers' own RBAC is what is tested."""
    import app.routers.department as dept_router
    import app.routers.grievances as grv_router
    from app.store import get_store
    from app.store.department_store import DepartmentStore
    from app.store.grievance_store import MemoryGrievanceStore

    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear(); get_store.cache_clear()
    ds, gs = DepartmentStore(), MemoryGrievanceStore()
    monkeypatch.setattr(dept_router, "get_department_store", lambda: ds)
    monkeypatch.setattr(grv_router, "get_department_store", lambda: ds)
    monkeypatch.setattr(grv_router, "get_grievance_store", lambda: gs)
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_optional_user, None)
    app.dependency_overrides.pop(get_current_user, None)
    get_settings.cache_clear(); get_store.cache_clear()


def _as(u):
    app.dependency_overrides[get_optional_user] = lambda: u
    app.dependency_overrides[get_current_user] = lambda: u


def test_rbac_owner_other_user_and_departments(prod):
    owner = _user("owner", Role.INDUSTRY_USER)
    other = _user("other", Role.INDUSTRY_USER)
    mpcb_admin = _user("adm", Role.DEPARTMENT_ADMIN, "dept-mpcb")
    fssai_admin = _user("fadm", Role.DEPARTMENT_ADMIN, "dept-fssai")

    _as(owner)
    pid = prod.post("/api/v1/projects", json={"name": "Owner Plant", "industry": "food"}).json()["id"]
    _as(mpcb_admin)
    app_row = prod.post("/api/v1/department/applications", json={
        "project_id": pid, "requirement_id": "REQ-0001", "department_id": "dept-mpcb"}).json()

    _as(owner)
    r = prod.post(f"/api/v1/projects/{pid}/grievances", json={**GOOD, "application_id": app_row["id"]})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    assert len(prod.get(f"/api/v1/projects/{pid}/grievances").json()) == 1

    # Another industry user: cannot see, read or file.
    _as(other)
    assert prod.get(f"/api/v1/projects/{pid}/grievances").status_code == 404
    assert prod.get(f"/api/v1/projects/{pid}/grievances/{gid}").status_code == 404
    assert prod.get(f"/api/v1/projects/{pid}/applications").status_code == 404
    assert prod.post(f"/api/v1/projects/{pid}/grievances",
                     json={**GOOD, "application_id": app_row["id"]}).status_code == 404
    # Industry users cannot reach government grievance routes.
    assert prod.get("/api/v1/department/grievances").status_code == 403

    # A different department cannot see or act on it.
    _as(fssai_admin)
    assert prod.get("/api/v1/department/grievances").json() == []
    assert prod.get(f"/api/v1/department/grievances/{gid}").status_code == 404
    assert prod.post(f"/api/v1/department/grievances/{gid}/transition",
                     json={"to_status": "UNDER_REVIEW"}).status_code == 404

    # The owning department can; but a government user cannot file as applicant.
    _as(mpcb_admin)
    assert len(prod.get("/api/v1/department/grievances").json()) == 1
    assert prod.post(f"/api/v1/projects/{pid}/grievances",
                     json={**GOOD, "application_id": app_row["id"]}).status_code == 403

    # Unauthenticated: fail closed.
    app.dependency_overrides.pop(get_optional_user, None)
    app.dependency_overrides.pop(get_current_user, None)
    assert prod.get(f"/api/v1/projects/{pid}/grievances").status_code == 401


def test_officer_role_cannot_assign(prod):
    owner = _user("owner", Role.INDUSTRY_USER)
    admin = _user("adm", Role.DEPARTMENT_ADMIN, "dept-mpcb")
    officer = _user("off", Role.DEPARTMENT_OFFICER, "dept-mpcb")
    _as(owner)
    pid = prod.post("/api/v1/projects", json={"name": "P", "industry": "food"}).json()["id"]
    _as(admin)
    a = prod.post("/api/v1/department/applications", json={
        "project_id": pid, "requirement_id": "REQ-0001", "department_id": "dept-mpcb"}).json()
    _as(owner)
    gid = prod.post(f"/api/v1/projects/{pid}/grievances", json={**GOOD, "application_id": a["id"]}).json()["id"]
    _as(officer)
    assert prod.post(f"/api/v1/department/grievances/{gid}/assign",
                     json={"officer_id": "du-demo-officer"}).status_code == 403


def test_supabase_grievance_store_request_shapes(monkeypatch):
    from app.store.grievance_store import SupabaseGrievanceStore

    calls = []

    def fake_req(self, method, path, **kw):
        calls.append((method, path, kw))
        if method == "POST" and path == "/grievances":
            return [{"id": "g1"}]
        if method == "GET" and path == "/grievances":
            return [{"id": "g1", "status": "OPEN"}]
        if method == "GET" and path == "/grievance_history":
            return []
        return None

    monkeypatch.setattr(SupabaseGrievanceStore, "_req", fake_req)
    s = SupabaseGrievanceStore.__new__(SupabaseGrievanceStore)
    actor = {"id": "u1", "name": "U", "role": "INDUSTRY_USER"}
    s.create({"project_id": "p", "application_id": "a", "department_id": "d",
              "category": "OTHER", "description": "x" * 12, "context_snapshot": {},
              "raised_by": "u1"}, actor)
    s.update("g1", {"status": "UNDER_REVIEW"}, frm="OPEN", to="UNDER_REVIEW", actor=actor, note=None)

    methods = [(m, p) for m, p, _ in calls]
    assert ("POST", "/grievances") in methods
    assert methods.count(("POST", "/grievance_history")) == 2  # append-only history rows
    patch = next(kw for m, p, kw in calls if m == "PATCH")
    assert patch["params"] == {"id": "eq.g1"} and patch["json"]["status"] == "UNDER_REVIEW"
    assert not any(m == "DELETE" for m, _, _ in calls)
