"""
SLA Intelligence tests.

Tests the government-only SLA dashboard, stage performance analytics,
at-risk/breach detection, aging, and sla_stage_targets integration.

SLA state is computed by _compute_sla_state() (single authoritative path).
Stage-level performance is computed from stage_history timestamps.
"""
import time


def _create_app(client, project_id="mahapharm", req_id="REQ-0001"):
    r = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": project_id,
            "requirement_id": req_id,
            "department_id": "dept-mpcb",
            "title": "SLA Test Application",
            "applicant_name": "Test Applicant",
        },
    )
    assert r.status_code == 201, r.json()
    return r.json()


def test_sla_dashboard_structure(client):
    """SLA dashboard returns expected keys from real data."""
    r = client.get("/api/v1/department/sla/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "kpis" in body
    assert "applications" in body
    assert "stage_performance" in body
    assert "breach_by_stage" in body

    kpis = body["kpis"]
    assert "total" in kpis
    assert "active" in kpis
    assert "within_sla" in kpis
    assert "at_risk" in kpis
    assert "breached" in kpis
    assert "aging_0_7d" in kpis
    assert "aging_7_30d" in kpis
    assert "aging_30_60d" in kpis
    assert "aging_over_60d" in kpis


def test_sla_dashboard_kpis_reflect_real_data(client):
    """Dashboard KPIs must reflect actual application counts."""
    _create_app(client)
    _create_app(client, req_id="REQ-0002")

    r = client.get("/api/v1/department/sla/dashboard")
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    # Both new apps should be WITHIN_SLA and counted in active
    assert kpis["total"] >= 2
    assert kpis["active"] >= 2
    # New apps are within SLA (just created)
    assert isinstance(kpis["within_sla"], int)
    assert isinstance(kpis["at_risk"], int)
    assert isinstance(kpis["breached"], int)
    # within + at_risk + breached + completed = total
    total_check = kpis["within_sla"] + kpis["at_risk"] + kpis["breached"] + kpis["completed"]
    assert total_check == kpis["total"]


def test_sla_within_on_new_application(client):
    """Freshly created application must be WITHIN_SLA (single authoritative path)."""
    app = _create_app(client)
    detail = client.get(f"/api/v1/department/applications/{app['id']}").json()
    assert detail["sla"]["state"] == "WITHIN_SLA"


def test_sla_completed_when_approved(client):
    """Application SLA becomes COMPLETED when approved."""
    app = _create_app(client)
    app_id = app["id"]
    for stage in ["UNDER_REVIEW", "RECOMMENDED", "APPROVED"]:
        r = client.post(
            f"/api/v1/department/applications/{app_id}/transition",
            json={"new_stage": stage},
        )
        assert r.status_code == 200
    detail = client.get(f"/api/v1/department/applications/{app_id}").json()
    assert detail["sla"]["state"] == "COMPLETED"


def test_sla_applications_endpoint(client):
    """SLA applications endpoint returns list with SLA status per application."""
    _create_app(client)
    r = client.get("/api/v1/department/sla/applications")
    assert r.status_code == 200
    body = r.json()
    assert "total" in body
    assert "items" in body
    assert body["total"] >= 1

    # Each item must have SLA fields
    item = body["items"][0]
    assert "sla_state" in item
    assert "elapsed_pct" in item
    assert "age_hours" in item
    assert item["sla_state"] in ("WITHIN_SLA", "AT_RISK", "BREACHED", "COMPLETED")


def test_sla_applications_filter_by_state(client):
    """Filter SLA applications by state."""
    _create_app(client)
    r = client.get("/api/v1/department/sla/applications", params={"sla_state": "WITHIN_SLA"})
    assert r.status_code == 200
    items = r.json()["items"]
    for item in items:
        assert item["sla_state"] == "WITHIN_SLA"


def test_sla_stage_performance_structure(client):
    """Stage performance returns per-stage metrics."""
    r = client.get("/api/v1/department/sla/stage-performance")
    assert r.status_code == 200
    perf = r.json()
    assert isinstance(perf, list)
    assert len(perf) > 0

    # Each entry has expected fields
    entry = perf[0]
    assert "stage" in entry
    assert "entry_count" in entry
    assert "completed_count" in entry
    assert "avg_duration_hours" in entry
    assert "median_duration_hours" in entry
    assert "target_hours" in entry  # from sla_stage_targets
    assert "vs_target" in entry


def test_sla_stage_targets_used_in_performance(client):
    """
    sla_stage_targets must be used in stage performance analytics (not ignored).
    Stages with configured targets should show target_hours.
    """
    r = client.get("/api/v1/department/sla/stage-performance")
    assert r.status_code == 200
    perf = r.json()

    # SUBMITTED should have a target (seeded at 48h in standard policy)
    submitted = next((p for p in perf if p["stage"] == "SUBMITTED"), None)
    assert submitted is not None
    assert submitted["target_hours"] == 48


def test_sla_stage_targets_list(client):
    """List SLA stage targets."""
    r = client.get("/api/v1/department/sla/stage-targets")
    assert r.status_code == 200
    targets = r.json()
    assert isinstance(targets, list)
    assert len(targets) >= 1  # seeded targets


def test_sla_stage_targets_create(client):
    """Create a new stage target."""
    # First create a policy to attach target to
    policy = client.post(
        "/api/v1/department/sla/policies",
        json={
            "name": "Test Policy for Stage Target",
            "duration_hours": 240,
            "warning_pct": 0.80,
            "description": "Test only",
        },
    )
    assert policy.status_code == 201
    policy_id = policy.json()["id"]

    r = client.post(
        "/api/v1/department/sla/stage-targets",
        json={
            "policy_id": policy_id,
            "stage": "UNDER_REVIEW",
            "target_hours": 120,
            "warning_pct": 0.75,
            "description": "Test stage target",
        },
    )
    assert r.status_code == 201
    target = r.json()
    assert target["target_hours"] == 120
    assert target["stage"] == "UNDER_REVIEW"


def test_sla_aging_buckets_correct(client):
    """Aging buckets reflect real age data."""
    _create_app(client)  # brand new app — will be in 0-7d bucket
    r = client.get("/api/v1/department/sla/dashboard")
    kpis = r.json()["kpis"]
    # Newly created app should be in aging_0_7d
    assert kpis["aging_0_7d"] >= 1
    # Buckets must not contain None
    assert isinstance(kpis["aging_0_7d"], int)
    assert isinstance(kpis["aging_7_30d"], int)
    assert isinstance(kpis["aging_30_60d"], int)
    assert isinstance(kpis["aging_over_60d"], int)


def test_breach_by_stage_structure(client):
    """breach_by_stage in SLA dashboard is a list of {stage, count}."""
    r = client.get("/api/v1/department/sla/dashboard")
    breach_by_stage = r.json()["breach_by_stage"]
    assert isinstance(breach_by_stage, list)
    for entry in breach_by_stage:
        assert "stage" in entry
        assert "count" in entry
        assert isinstance(entry["count"], int)


def test_sla_dashboard_applications_sorted_by_urgency(client):
    """
    Applications in SLA dashboard are sorted: BREACHED first, AT_RISK second,
    then WITHIN_SLA. COMPLETED last.
    """
    _create_app(client)
    _create_app(client, req_id="REQ-0002")
    r = client.get("/api/v1/department/sla/dashboard")
    apps = r.json()["applications"]
    if len(apps) < 2:
        return  # not enough data to check order

    # Verify state order is monotonically non-decreasing in urgency
    sla_order = {"BREACHED": 0, "AT_RISK": 1, "WITHIN_SLA": 2, "COMPLETED": 3}
    for i in range(len(apps) - 1):
        a = sla_order.get(apps[i]["sla_state"], 9)
        b = sla_order.get(apps[i + 1]["sla_state"], 9)
        assert a <= b, f"Order violation: {apps[i]['sla_state']} before {apps[i+1]['sla_state']}"


def test_sla_policies_seeded(client):
    """Three demo SLA policies are seeded and have descriptions."""
    r = client.get("/api/v1/department/sla/policies")
    assert r.status_code == 200
    policies = r.json()
    assert len(policies) >= 3
    for p in policies:
        assert p["description"], f"Policy {p['name']} has no description"
        assert "demo" in p["description"].lower() or "configurable" in p["description"].lower()


def test_sla_policies_backward_compat(client):
    """Old /api/v1/department/sla/policies path still works (backward compat)."""
    r = client.get("/api/v1/department/sla/policies")
    assert r.status_code == 200


def test_sla_not_exposed_to_industry_portal(client):
    """
    SLA endpoints must return data only for government users.
    In demo mode, all callers are demo manager — this test verifies
    the structure, not actual authentication (which needs a real Supabase project).
    Actual authentication enforcement is tested in test_auth.py.
    """
    r = client.get("/api/v1/department/sla/dashboard")
    assert r.status_code == 200  # demo mode: passes through
    # Verify no SLA data leaks to any industry-facing routes
    # Industry routes (/api/v1/projects, /api/v1/requirements, /api/v1/evaluate)
    # should NOT have SLA fields
    r2 = client.get("/api/v1/projects/mahapharm")
    body = r2.json()
    assert "sla" not in body
    assert "sla_state" not in body
    assert "breach" not in body
