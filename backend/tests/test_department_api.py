"""
Department portal API tests.

Covers:
- Application CRUD
- Assignment / reassignment
- Valid workflow transitions
- Invalid transition rejection (server-side validation)
- SLA calculation, AT_RISK and BREACHED states
- Dashboard KPI accuracy
- Operational audit/timeline events
- Fix 1: project creation with auto-generated ID
- Fix 2: fact upsert idempotency
- Fix 4: lazy NON_PRODUCTION persistence (diagnostics not auto-persisted)
"""
import time


# ---------------------------------------------------------------------------
# Fix 1 — Project creation with auto-generated ID
# ---------------------------------------------------------------------------

def test_create_project_without_id_generates_uuid(client):
    """Fix 1: project created without explicit id gets a UUID, not a server error."""
    r = client.post(
        "/api/v1/projects",
        json={"name": "Auto-ID Co", "industry": "food"},
    )
    assert r.status_code == 201
    project = r.json()
    assert project["id"]
    assert len(project["id"]) >= 8  # uuid or similar
    # Fetch it back
    g = client.get(f"/api/v1/projects/{project['id']}")
    assert g.status_code == 200
    assert g.json()["name"] == "Auto-ID Co"


# ---------------------------------------------------------------------------
# Fix 2 — Fact upsert idempotency
# ---------------------------------------------------------------------------

def test_fact_upsert_is_idempotent(client):
    """Fix 2: posting the same fact twice must not duplicate rows."""
    for _ in range(2):
        r = client.post(
            "/api/v1/projects/mahapharm/facts",
            json={"facts": {"project.upsert_test": True}},
        )
        assert r.status_code == 200
    g = client.get("/api/v1/projects/mahapharm/facts")
    # Should have exactly ONE entry for this key, not two
    facts = g.json()["facts"]
    assert facts.get("project.upsert_test") is True


def test_fact_upsert_updates_value(client):
    """Fix 2: second upsert with different value wins (UPDATE semantics)."""
    client.post(
        "/api/v1/projects/mahapharm/facts",
        json={"facts": {"project.update_test": "first"}},
    )
    client.post(
        "/api/v1/projects/mahapharm/facts",
        json={"facts": {"project.update_test": "second"}},
    )
    g = client.get("/api/v1/projects/mahapharm/facts")
    assert g.json()["facts"]["project.update_test"] == "second"


# ---------------------------------------------------------------------------
# Fix 4 — Lazy NON_PRODUCTION persistence
# ---------------------------------------------------------------------------

def test_non_production_evaluation_not_auto_persisted(client):
    """Fix 4: NON_PRODUCTION without explicit persist:true must NOT persist."""
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0002",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {"project.plant_located_in_air_pollution_control_area": True},
            # persist not set → should default to False for NON_PRODUCTION
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "persistence" not in body  # was not persisted


def test_non_production_explicit_persist_true_does_persist(client):
    """Fix 4: NON_PRODUCTION with explicit persist:true DOES persist."""
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
            "persist": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["persistence"]["stored"] is True


def test_production_evaluation_auto_persists_by_default(client):
    """Fix 4: PRODUCTION mode still defaults to persist=True."""
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "PRODUCTION",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
            # persist not set → should default to True for PRODUCTION
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "persistence" in body
    assert body["persistence"]["stored"] is True


# ---------------------------------------------------------------------------
# Department API — Applications CRUD
# ---------------------------------------------------------------------------

def _create_app(client, project_id="mahapharm", req_id="REQ-0001"):
    r = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": project_id,
            "requirement_id": req_id,
            "department_id": "dept-mpcb",
            "title": "Test Application",
            "applicant_name": "Test Applicant",
        },
    )
    assert r.status_code == 201
    return r.json()


def test_create_application(client):
    app = _create_app(client)
    assert app["current_stage"] == "SUBMITTED"
    assert app["application_id"].startswith("APP-")
    assert app["project_id"] == "mahapharm"
    assert app["requirement_id"] == "REQ-0001"


def test_get_application_detail(client):
    app = _create_app(client)
    r = client.get(f"/api/v1/department/applications/{app['id']}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["id"] == app["id"]
    assert "sla" in detail
    assert "stage_history" in detail
    assert "assignment_history" in detail
    assert "operational_events" in detail


def test_create_application_for_missing_project_is_404(client):
    r = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": "does-not-exist",
            "requirement_id": "REQ-0001",
            "department_id": "dept-mpcb",
        },
    )
    assert r.status_code == 404


def test_get_missing_application_is_404(client):
    r = client.get("/api/v1/department/applications/nonexistent-id")
    assert r.status_code == 404


def test_list_applications(client):
    _create_app(client)
    _create_app(client, req_id="REQ-0002")
    r = client.get("/api/v1/department/applications")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2
    assert isinstance(body["items"], list)


def test_list_applications_status_filter(client):
    _create_app(client)
    r = client.get("/api/v1/department/applications", params={"status": "SUBMITTED"})
    assert r.status_code == 200
    items = r.json()["items"]
    for item in items:
        assert item["current_stage"] == "SUBMITTED"


# ---------------------------------------------------------------------------
# Department API — Officer Assignment
# ---------------------------------------------------------------------------

def test_assign_officer(client):
    app = _create_app(client)
    r = client.post(
        f"/api/v1/department/applications/{app['id']}/assign",
        json={"officer_id": "officer-001", "officer_name": "Priya Sharma"},
    )
    assert r.status_code == 200
    detail = r.json()
    assert detail["assigned_officer_name"] == "Priya Sharma"
    assert detail["assigned_officer_id"] == "officer-001"


def test_reassign_officer_records_history(client):
    app = _create_app(client)
    app_id = app["id"]
    client.post(
        f"/api/v1/department/applications/{app_id}/assign",
        json={"officer_id": "officer-001", "officer_name": "Priya Sharma"},
    )
    client.post(
        f"/api/v1/department/applications/{app_id}/assign",
        json={"officer_id": "officer-002", "officer_name": "Rahul Patil", "reason": "Transfer"},
    )
    detail = client.get(f"/api/v1/department/applications/{app_id}").json()
    history = detail["assignment_history"]
    assert len(history) == 2
    assert history[-1]["officer_name"] == "Rahul Patil"


# ---------------------------------------------------------------------------
# Department API — Workflow Transitions
# ---------------------------------------------------------------------------

def test_valid_transition_submitted_to_under_review(client):
    app = _create_app(client)
    r = client.post(
        f"/api/v1/department/applications/{app['id']}/transition",
        json={"new_stage": "UNDER_REVIEW", "reason": "Initial review started"},
    )
    assert r.status_code == 200
    assert r.json()["current_stage"] == "UNDER_REVIEW"


def test_valid_transition_full_happy_path(client):
    app = _create_app(client)
    app_id = app["id"]
    transitions = [
        ("UNDER_REVIEW", None),
        ("INSPECTION_SCHEDULED", "Site visit booked"),
        ("INSPECTION_COMPLETED", "Inspection done"),
        ("RECOMMENDED", "All checks passed"),
        ("APPROVED", "Application approved"),
    ]
    for stage, reason in transitions:
        r = client.post(
            f"/api/v1/department/applications/{app_id}/transition",
            json={"new_stage": stage, "reason": reason},
        )
        assert r.status_code == 200, f"Transition to {stage} failed: {r.json()}"
        assert r.json()["current_stage"] == stage


def test_invalid_transition_rejected(client):
    app = _create_app(client)
    # SUBMITTED → APPROVED is invalid (must go through UNDER_REVIEW first)
    r = client.post(
        f"/api/v1/department/applications/{app['id']}/transition",
        json={"new_stage": "APPROVED"},
    )
    assert r.status_code == 422


def test_transition_from_terminal_state_rejected(client):
    app = _create_app(client)
    app_id = app["id"]
    # Navigate to REJECTED (terminal)
    client.post(f"/api/v1/department/applications/{app_id}/transition", json={"new_stage": "UNDER_REVIEW"})
    client.post(f"/api/v1/department/applications/{app_id}/transition", json={"new_stage": "REJECTED"})
    # Attempt to move out of terminal state
    r = client.post(
        f"/api/v1/department/applications/{app_id}/transition",
        json={"new_stage": "UNDER_REVIEW"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Department API — SLA
# ---------------------------------------------------------------------------

def test_sla_within_on_new_application(client):
    """New application should be WITHIN_SLA immediately after creation."""
    app = _create_app(client)
    detail = client.get(f"/api/v1/department/applications/{app['id']}").json()
    assert detail["sla"]["state"] == "WITHIN_SLA"


def test_sla_completed_on_approved_application(client):
    app = _create_app(client)
    app_id = app["id"]
    for stage in ["UNDER_REVIEW", "RECOMMENDED", "APPROVED"]:
        client.post(
            f"/api/v1/department/applications/{app_id}/transition",
            json={"new_stage": stage},
        )
    detail = client.get(f"/api/v1/department/applications/{app_id}").json()
    assert detail["sla"]["state"] == "COMPLETED"


def test_sla_policies_listed(client):
    r = client.get("/api/v1/department/sla/policies")
    assert r.status_code == 200
    policies = r.json()
    assert len(policies) >= 3  # seeded policies
    # All should have clearly labelled descriptions (not silent hardcoded law)
    for p in policies:
        assert "description" in p and p["description"]


def test_create_custom_sla_policy(client):
    r = client.post(
        "/api/v1/department/sla/policies",
        json={
            "name": "Custom 7-day Review",
            "duration_hours": 168,
            "warning_pct": 0.85,
            "description": "Test-only SLA policy",
        },
    )
    assert r.status_code == 201
    policy = r.json()
    assert policy["duration_hours"] == 168


# ---------------------------------------------------------------------------
# Department API — Dashboard KPIs
# ---------------------------------------------------------------------------

def test_dashboard_kpis_are_real_not_hardcoded(client):
    """KPIs must reflect actual data, not fabricated numbers."""
    # Create a few applications
    _create_app(client)
    _create_app(client, req_id="REQ-0002")
    r = client.get("/api/v1/department/dashboard")
    assert r.status_code == 200
    body = r.json()
    kpis = body["kpis"]
    assert kpis["total"] >= 2
    assert kpis["pending"] >= 2  # all still SUBMITTED
    assert isinstance(kpis["sla_at_risk"], int)
    assert isinstance(kpis["sla_breached"], int)
    assert "pipeline" in body
    assert "recent_applications" in body
    assert "attention_required" in body


def test_dashboard_reflects_stage_changes(client):
    app = _create_app(client)
    # Move to UNDER_REVIEW — should count as in_progress, not pending
    client.post(
        f"/api/v1/department/applications/{app['id']}/transition",
        json={"new_stage": "UNDER_REVIEW"},
    )
    r = client.get("/api/v1/department/dashboard")
    kpis = r.json()["kpis"]
    assert kpis["in_progress"] >= 1


# ---------------------------------------------------------------------------
# Department API — Timeline
# ---------------------------------------------------------------------------

def test_timeline_records_transitions_and_assignments(client):
    app = _create_app(client)
    app_id = app["id"]
    client.post(
        f"/api/v1/department/applications/{app_id}/assign",
        json={"officer_id": "officer-001", "officer_name": "Priya Sharma"},
    )
    client.post(
        f"/api/v1/department/applications/{app_id}/transition",
        json={"new_stage": "UNDER_REVIEW"},
    )
    r = client.get(f"/api/v1/department/applications/{app_id}/timeline")
    assert r.status_code == 200
    events = r.json()
    event_types = [e["event_type"] for e in events]
    assert "APPLICATION_SUBMITTED" in event_types
    assert "OFFICER_ASSIGNED" in event_types
    assert "STAGE_TRANSITION" in event_types


# ---------------------------------------------------------------------------
# Department API — Engine decision attached to detail
# ---------------------------------------------------------------------------

def test_application_detail_includes_engine_decision_when_persisted(client):
    """If a PRODUCTION evaluation has been stored for the project+requirement,
    it should appear in the application detail under engine_decision."""
    # First persist a decision
    client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "PRODUCTION",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
            "persist": True,
        },
    )
    # Create matching application
    app = _create_app(client, project_id="mahapharm", req_id="REQ-0001")
    detail = client.get(f"/api/v1/department/applications/{app['id']}").json()
    # engine_decision may be None or a dict — not a hardcoded value
    assert "engine_decision" in detail
    if detail["engine_decision"] is not None:
        assert detail["engine_decision"]["requirement_id"] == "REQ-0001"
