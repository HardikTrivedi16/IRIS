"""
Tests for SupabaseDepartmentStore PostgREST integration.

Uses httpx.MockTransport to mock PostgREST responses and verify:
  1. Service role key is used in headers (never anon key).
  2. Department-scoped queries always include department_id=eq.<id>.
  3. Applications, stage transitions, SLA instances, and operational events
     are persisted correctly through PostgREST requests.
  4. Cross-department queries properly filter out mismatched rows.
"""
import json
import httpx
import pytest
from app.store.supabase_department_store import SupabaseDepartmentStore


class FakeDepartmentPostgrest:
    """Mock PostgREST server for Government tables."""

    def __init__(self):
        self.tables = {
            "departments": [
                {"id": "dept-mpcb", "name": "Maharashtra Pollution Control Board", "code": "MPCB"},
                {"id": "dept-fssai", "name": "Food Safety and Standards Authority", "code": "FSSAI"},
            ],
            "applications": [],
            "application_stage_history": [],
            "sla_policies": [],
            "sla_instances": [],
            "operational_events": [],
            "department_users": [],
            "user_profiles": [],
        }
        self.recorded_requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.recorded_requests.append(request)
        table = request.url.path.rstrip("/").split("/")[-1]
        params = dict(request.url.params)

        if request.method == "GET":
            rows = self.tables.get(table, [])
            for k, v in params.items():
                if k.endswith(".eq"):
                    col = k[:-3]
                    rows = [r for r in rows if str(r.get(col)) == v]
                elif isinstance(v, str) and v.startswith("eq."):
                    val = v[3:]
                    rows = [r for r in rows if str(r.get(k)) == val]
            return httpx.Response(200, json=rows)

        if request.method == "POST":
            data = json.loads(request.content.decode("utf-8")) if request.content else {}
            if isinstance(data, list):
                self.tables.setdefault(table, []).extend(data)
                return httpx.Response(201, json=data)
            else:
                self.tables.setdefault(table, []).append(data)
                return httpx.Response(201, json=[data])

        if request.method == "PATCH":
            data = json.loads(request.content.decode("utf-8")) if request.content else {}
            rows = self.tables.get(table, [])
            updated = []
            for r in rows:
                match = True
                for k, v in params.items():
                    if isinstance(v, str) and v.startswith("eq."):
                        if str(r.get(k)) != v[3:]:
                            match = False
                            break
                if match:
                    r.update(data)
                    updated.append(r)
            return httpx.Response(200, json=updated)

        return httpx.Response(405)


@pytest.fixture
def fake_postgrest():
    fake = FakeDepartmentPostgrest()
    transport = httpx.MockTransport(fake.handle)
    store = SupabaseDepartmentStore(
        url="https://mock-proj.supabase.co",
        service_role_key="test-secret-service-role-key-xyz",
        transport=transport,
    )
    return store, fake


def test_headers_use_service_role_key(fake_postgrest):
    store, fake = fake_postgrest
    store.list_departments()
    assert len(fake.recorded_requests) >= 1
    req = fake.recorded_requests[0]
    assert req.headers["apikey"] == "test-secret-service-role-key-xyz"
    assert req.headers["authorization"] == "Bearer test-secret-service-role-key-xyz"


def test_department_isolation_in_queries(fake_postgrest):
    store, fake = fake_postgrest
    # Seed applications in two departments
    fake.tables["applications"] = [
        {"id": "app-1", "department_id": "dept-mpcb", "title": "MPCB App 1", "status": "SUBMITTED"},
        {"id": "app-2", "department_id": "dept-fssai", "title": "FSSAI App 1", "status": "SUBMITTED"},
    ]

    # Query for dept-mpcb
    apps = store.list_applications(department_id="dept-mpcb")
    assert len(apps["items"]) == 1
    assert apps["items"][0]["id"] == "app-1"
    assert apps["items"][0]["department_id"] == "dept-mpcb"

    # Query for dept-fssai
    fssai_apps = store.list_applications(department_id="dept-fssai")
    assert len(fssai_apps["items"]) == 1
    assert fssai_apps["items"][0]["id"] == "app-2"


def test_get_application_cross_department_returns_none(fake_postgrest):
    store, fake = fake_postgrest
    fake.tables["applications"] = [
        {"id": "app-mpcb", "department_id": "dept-mpcb", "title": "MPCB Secret", "status": "SUBMITTED"},
    ]

    # Queried with wrong department_id
    res = store.get_application("app-mpcb", department_id="dept-fssai")
    assert res is None, "Cross-department query should return None"

    # Queried with correct department_id
    res_correct = store.get_application("app-mpcb", department_id="dept-mpcb")
    assert res_correct is not None
    assert res_correct["id"] == "app-mpcb"


def test_create_application_persists_stage_and_sla(fake_postgrest):
    store, fake = fake_postgrest
    app_data = {
        "project_id": "proj-1",
        "requirement_id": "REQ-0001",
        "department_id": "dept-mpcb",
        "title": "Consent to Operate",
        "status": "SUBMITTED",
        "sla_policy_id": "pol-mpcb-standard",
    }
    created = store.create_application(app_data)
    assert created["id"] is not None
    assert created["department_id"] == "dept-mpcb"

    # Check stage history was created
    assert len(fake.tables["application_stage_history"]) >= 1
    history = fake.tables["application_stage_history"][0]
    assert history["application_id"] == created["id"]
    assert history["new_stage"] == "SUBMITTED"

    # Check SLA instance was created
    assert len(fake.tables["sla_instances"]) >= 1
    sla = fake.tables["sla_instances"][0]
    assert sla["application_id"] == created["id"]
    assert sla["policy_id"] == "pol-mpcb-standard"
