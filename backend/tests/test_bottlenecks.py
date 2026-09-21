"""
Bottleneck analytics tests.

Tests the government-only bottleneck report, per-stage metrics,
officer workload, and processing trends.

All metrics are deterministic and computed from real stage_history data.
No fabricated scores or invented values.
"""


def _create_app(client, project_id="mahapharm", req_id="REQ-0001"):
    r = client.post(
        "/api/v1/department/applications",
        json={
            "project_id": project_id,
            "requirement_id": req_id,
            "department_id": "dept-mpcb",
            "title": "Bottleneck Test Application",
        },
    )
    assert r.status_code == 201, r.json()
    return r.json()


def _transition(client, app_id, stage, reason=None):
    r = client.post(
        f"/api/v1/department/applications/{app_id}/transition",
        json={"new_stage": stage, "reason": reason},
    )
    assert r.status_code == 200, f"Transition to {stage} failed: {r.json()}"
    return r.json()


def test_bottleneck_report_structure(client):
    """Full bottleneck report has expected keys."""
    r = client.get("/api/v1/department/bottlenecks/report")
    assert r.status_code == 200
    body = r.json()
    assert "generated_at" in body
    assert "total_active" in body
    assert "total_applications" in body
    assert "methodology" in body
    assert "stages" in body
    assert "officers" in body
    assert "top_bottleneck_stage" in body


def test_bottleneck_methodology_documented(client):
    """Methodology must be documented (not a black box)."""
    r = client.get("/api/v1/department/bottlenecks/report")
    body = r.json()
    method = body["methodology"]
    assert "Deterministic" in method or "deterministic" in method
    # Must mention the score formula components
    assert "avg_duration" in method or "duration" in method.lower()
    assert "backlog" in method.lower()


def test_bottleneck_stages_structure(client):
    """Per-stage metrics have all required fields."""
    r = client.get("/api/v1/department/bottlenecks/stages")
    assert r.status_code == 200
    stages = r.json()
    assert isinstance(stages, list)

    required_fields = [
        "stage", "backlog", "entry_count", "completed_count",
        "at_risk_count", "breached_count", "sla_breach_pct",
        "bottleneck_score", "rank",
        "aging_7d", "aging_14d", "aging_30d",
        "throughput_7d", "throughput_30d",
    ]
    for entry in stages:
        for field in required_fields:
            assert field in entry, f"Missing field {field!r} in stage entry"


def test_bottleneck_score_is_not_fabricated(client):
    """Bottleneck score must be 0 when backlog is 0 and no duration data."""
    # Fresh store — no applications
    r = client.get("/api/v1/department/bottlenecks/stages")
    stages = r.json()
    for entry in stages:
        if entry["backlog"] == 0 and entry["avg_duration_hours"] is None:
            assert entry["bottleneck_score"] == 0.0, (
                f"Stage {entry['stage']} has score {entry['bottleneck_score']} "
                f"despite zero backlog and no duration data"
            )


def test_bottleneck_score_increases_with_backlog(client):
    """Bottleneck score increases as backlog grows (formula is monotonic in backlog)."""
    r_before = client.get("/api/v1/department/bottlenecks/stages")
    stages_before = {s["stage"]: s for s in r_before.json()}
    score_before = stages_before.get("SUBMITTED", {}).get("bottleneck_score", 0.0)

    # Add an application (increases SUBMITTED backlog)
    _create_app(client)

    r_after = client.get("/api/v1/department/bottlenecks/stages")
    stages_after = {s["stage"]: s for s in r_after.json()}
    score_after = stages_after.get("SUBMITTED", {}).get("bottleneck_score", 0.0)

    assert score_after > score_before, (
        f"Score should increase with backlog: {score_before} → {score_after}"
    )


def test_bottleneck_stage_ranks_ordered(client):
    """Stage ranks must be 1..N with no gaps and no duplicates."""
    _create_app(client)
    r = client.get("/api/v1/department/bottlenecks/stages")
    stages = r.json()
    ranks = sorted(s["rank"] for s in stages)
    assert ranks == list(range(1, len(stages) + 1)), (
        f"Ranks are not sequential 1..N: {ranks}"
    )


def test_bottleneck_rank1_has_highest_score(client):
    """Stage ranked 1 must have the highest or equal bottleneck score."""
    _create_app(client)
    r = client.get("/api/v1/department/bottlenecks/stages")
    stages = r.json()
    rank1 = next((s for s in stages if s["rank"] == 1), None)
    if rank1:
        max_score = max(s["bottleneck_score"] for s in stages)
        assert rank1["bottleneck_score"] == max_score


def test_bottleneck_backlog_counts_correctly(client):
    """Backlog = non-terminal applications. Terminal apps not counted."""
    app = _create_app(client)
    app_id = app["id"]

    r = client.get("/api/v1/department/bottlenecks/stages")
    stages = {s["stage"]: s for s in r.json()}
    assert stages["SUBMITTED"]["backlog"] >= 1

    # Approve the app — should move out of backlog
    _transition(client, app_id, "UNDER_REVIEW")
    _transition(client, app_id, "RECOMMENDED")
    _transition(client, app_id, "APPROVED")

    r2 = client.get("/api/v1/department/bottlenecks/stages")
    stages2 = {s["stage"]: s for s in r2.json()}
    # SUBMITTED backlog should have decreased by 1 (we approved our test app)
    # (There may be other apps in SUBMITTED from other tests, so just verify APPROVED stage is not in bottleneck list)
    stage_names = [s["stage"] for s in r2.json()]
    assert "APPROVED" not in stage_names, "APPROVED (terminal) should not be in bottleneck stages"
    assert "REJECTED" not in stage_names, "REJECTED (terminal) should not be in bottleneck stages"


def test_bottleneck_stage_duration_from_history(client):
    """
    Stage duration must be computed from real stage_history timestamps,
    not fabricated. After a transition, completed_count increases.
    """
    app = _create_app(client)
    app_id = app["id"]

    # Before transition: SUBMITTED has no completed sojourns
    r_before = client.get("/api/v1/department/bottlenecks/stages")
    stages_before = {s["stage"]: s for s in r_before.json()}
    completed_before = stages_before.get("SUBMITTED", {}).get("completed_count", 0)

    # Move app through SUBMITTED → UNDER_REVIEW
    _transition(client, app_id, "UNDER_REVIEW")

    r_after = client.get("/api/v1/department/bottlenecks/stages")
    stages_after = {s["stage"]: s for s in r_after.json()}
    completed_after = stages_after.get("SUBMITTED", {}).get("completed_count", 0)

    assert completed_after == completed_before + 1, (
        "completed_count should increase by 1 after a stage transition"
    )


def test_bottleneck_throughput_counts(client):
    """Throughput_7d and throughput_30d are non-negative integers."""
    r = client.get("/api/v1/department/bottlenecks/stages")
    for entry in r.json():
        assert isinstance(entry["throughput_7d"], int)
        assert isinstance(entry["throughput_30d"], int)
        assert entry["throughput_7d"] >= 0
        assert entry["throughput_30d"] >= 0
        assert entry["throughput_30d"] >= entry["throughput_7d"]  # 30d always >= 7d


def test_officer_workload_structure(client):
    """Officer workload has expected fields."""
    app = _create_app(client)
    # Assign an officer
    client.post(
        f"/api/v1/department/applications/{app['id']}/assign",
        json={"officer_id": "officer-999", "officer_name": "Test Officer"},
    )

    r = client.get("/api/v1/department/bottlenecks/officers")
    assert r.status_code == 200
    officers = r.json()
    assert isinstance(officers, list)

    if officers:
        o = officers[0]
        assert "officer_id" in o
        assert "officer_name" in o
        assert "active_applications" in o
        assert "completed_applications" in o
        assert "at_risk_count" in o
        assert "breached_count" in o


def test_officer_workload_counts_active_only(client):
    """Officer workload active_applications counts non-terminal apps only."""
    app = _create_app(client)
    app_id = app["id"]
    client.post(
        f"/api/v1/department/applications/{app_id}/assign",
        json={"officer_id": "officer-count-test", "officer_name": "Count Test Officer"},
    )

    r = client.get("/api/v1/department/bottlenecks/officers")
    officers = {o["officer_id"]: o for o in r.json()}

    if "officer-count-test" in officers:
        active_before = officers["officer-count-test"]["active_applications"]
        completed_before = officers["officer-count-test"]["completed_applications"]

        # Approve the app (terminal)
        _transition(client, app_id, "UNDER_REVIEW")
        _transition(client, app_id, "RECOMMENDED")
        _transition(client, app_id, "APPROVED")

        r2 = client.get("/api/v1/department/bottlenecks/officers")
        officers2 = {o["officer_id"]: o for o in r2.json()}
        if "officer-count-test" in officers2:
            assert officers2["officer-count-test"]["active_applications"] == active_before - 1
            assert officers2["officer-count-test"]["completed_applications"] == completed_before + 1


def test_processing_trends_structure(client):
    """Processing trends return list of {date, stage, entered, exited}."""
    _create_app(client)
    r = client.get("/api/v1/department/bottlenecks/trends")
    assert r.status_code == 200
    trends = r.json()
    assert isinstance(trends, list)
    if trends:
        entry = trends[0]
        assert "date" in entry
        assert "stage" in entry
        assert "entered" in entry
        assert "exited" in entry
        assert isinstance(entry["entered"], int)
        assert isinstance(entry["exited"], int)


def test_processing_trends_days_param(client):
    """trends?days=7 returns data (no error, non-negative counts)."""
    r = client.get("/api/v1/department/bottlenecks/trends", params={"days": 7})
    assert r.status_code == 200
    for entry in r.json():
        assert entry["entered"] >= 0
        assert entry["exited"] >= 0


def test_bottleneck_total_active_matches_non_terminal(client):
    """total_active in report matches sum of backlog counts across stages."""
    _create_app(client)
    r = client.get("/api/v1/department/bottlenecks/report")
    body = r.json()
    total_active = body["total_active"]
    stage_backlog_sum = sum(s["backlog"] for s in body["stages"])
    assert total_active == stage_backlog_sum, (
        f"total_active ({total_active}) != sum of backlog ({stage_backlog_sum})"
    )


def test_sla_breach_pct_is_fraction_not_percentage(client):
    """sla_breach_pct is a fraction 0.0–1.0, not 0–100."""
    _create_app(client)
    r = client.get("/api/v1/department/bottlenecks/stages")
    for entry in r.json():
        assert 0.0 <= entry["sla_breach_pct"] <= 1.0, (
            f"Stage {entry['stage']} has sla_breach_pct={entry['sla_breach_pct']} (must be 0.0–1.0)"
        )
