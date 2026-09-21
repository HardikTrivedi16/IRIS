"""P1-J — bottleneck explanation exposes components; the score is a labelled heuristic."""
from datetime import datetime, timezone

import pytest

from app.bottleneck_explain import SCORE_CLASSIFICATION, explain_bottlenecks


def _make_apps(client, n, stage=None):
    ids = []
    for _ in range(n):
        a = client.post("/api/v1/department/applications", json={
            "project_id": "freshbite", "requirement_id": "REQ-0001", "department_id": "dept-mpcb",
            "sla_policy_id": "sla-standard-30d"}).json()
        if stage:
            client.post(f"/api/v1/department/applications/{a['id']}/transition",
                        json={"new_stage": stage, "reason": "test"})
        ids.append(a["id"])
    return ids


def test_contributions_sum_to_existing_score(client):
    _make_apps(client, 3)
    _make_apps(client, 2, stage="UNDER_REVIEW")
    body = client.get("/api/v1/department/bottlenecks/explanation").json()
    report = client.get("/api/v1/department/bottlenecks/report").json()
    by_stage = {s["stage"]: s for s in report["stages"]}
    assert body["stages"]
    for s in body["stages"]:
        total = sum(s["heuristic_contributions"].values())
        assert total == pytest.approx(s["heuristic_score"], abs=1e-3)
        # Explanation never re-scores: same value and rank as the report.
        assert s["heuristic_score"] == by_stage[s["stage"]]["bottleneck_score"]
        assert s["rank_by_heuristic"] == by_stage[s["stage"]]["rank"]
        assert s["components"]["backlog"] == by_stage[s["stage"]]["backlog"]


def test_affected_applications_are_those_currently_in_stage(client):
    submitted = _make_apps(client, 2)
    review = _make_apps(client, 1, stage="UNDER_REVIEW")
    body = client.get("/api/v1/department/bottlenecks/explanation").json()
    stages = {s["stage"]: s for s in body["stages"]}
    assert {a["id"] for a in stages["SUBMITTED"]["affected_applications"]} == set(submitted)
    assert {a["id"] for a in stages["UNDER_REVIEW"]["affected_applications"]} == set(review)


def test_score_labelled_heuristic_and_no_causal_or_predictive_claims(client):
    body = client.get("/api/v1/department/bottlenecks/explanation").json()
    assert body["score_classification"] == SCORE_CLASSIFICATION == "PROTOTYPE_OPERATIONAL_HEURISTIC"
    text = " ".join(body["notes"]).lower()
    assert "not cause" in text and "no prediction" in text
    for forbidden in ("predicted", "forecast", "root cause", "caused by"):
        assert forbidden not in text


def test_synthetic_and_unclassified_counts():
    apps = [
        {"id": "1", "current_stage": "SUBMITTED", "created_at": "2026-09-01T00:00:00+00:00",
         "data_classification": "SYNTHETIC_DEMO", "sla": {"state": "BREACHED"}},
        {"id": "2", "current_stage": "APPROVED", "created_at": "2026-09-01T00:00:00+00:00",
         "completed_at": "2026-09-05T00:00:00+00:00", "data_classification": None, "sla": {}},
    ]
    out = explain_bottlenecks({"stages": [{"stage": "SUBMITTED", "backlog": 1, "rank": 1,
                                          "avg_duration_hours": None, "sla_breach_pct": 1.0,
                                          "bottleneck_score": 25.35}]}, apps,
                              now=datetime(2026, 9, 2, tzinfo=timezone.utc))
    assert out["data"] == {"applications_in_scope": 2, "synthetic_demo": 1, "unclassified": 1}
    assert out["notes"][0].startswith("SYNTHETIC DEMO DATA")
    [s] = out["stages"]
    assert [a["id"] for a in s["affected_applications"]] == ["1"]  # completed app excluded
    assert s["affected_applications"][0]["age_hours"] == 24.0


def test_industry_user_forbidden(client):
    from app.main import app
    from app.security import CurrentUser, Role, get_current_user
    ind = CurrentUser(user_id="i", email="i@x", role=Role.INDUSTRY_USER, name="i", is_demo=False)
    app.dependency_overrides[get_current_user] = lambda: ind
    try:
        assert client.get("/api/v1/department/bottlenecks/explanation").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
