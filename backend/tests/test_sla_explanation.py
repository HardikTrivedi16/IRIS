"""P1-I — the SLA explanation must equal the actual calculation."""
from datetime import datetime, timedelta, timezone

import pytest

from app.sla_explain import explain_sla
from app.store.department_store import _compute_sla_state

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
POLICY = {"id": "p", "name": "Demo 10-day", "duration_hours": 240, "warning_pct": 0.75,
          "description": "Demo configurable policy"}
TARGET = {"stage": "UNDER_REVIEW", "target_hours": 48, "warning_pct": 0.5, "description": "Demo target"}


def _app(**over):
    a = {"id": "a1", "application_id": "APP-1", "created_at": START.isoformat(), "completed_at": None,
         "current_stage": "UNDER_REVIEW",
         "stage_history": [{"new_stage": "UNDER_REVIEW", "created_at": (START + timedelta(hours=10)).isoformat()}]}
    a.update(over)
    return a


@pytest.mark.parametrize("hours,expected", [
    (10, "WITHIN_SLA"),
    (179.9, "WITHIN_SLA"),
    (180, "AT_RISK"),     # 75% of 240 h
    (239.9, "AT_RISK"),
    (240, "BREACHED"),
    (300, "BREACHED"),
])
def test_state_equals_authoritative_calculation(hours, expected):
    now = START + timedelta(hours=hours)
    exp = explain_sla(_app(), POLICY, TARGET, now=now)
    auth = _compute_sla_state(POLICY, START.isoformat(), None, now=now)
    assert exp["state"] == expected == (auth["state"].value if hasattr(auth["state"], "value") else auth["state"])
    assert exp["clock"]["due_at"] == auth["due_at"]
    assert exp["clock"]["warning_at"] == auth["warning_at"]
    assert exp["clock"]["elapsed_pct"] == auth["elapsed_pct"]
    assert exp["clock"]["elapsed_hours"] == round(hours, 2)


def test_remaining_and_overdue_hours():
    within = explain_sla(_app(), POLICY, TARGET, now=START + timedelta(hours=100))
    assert within["clock"]["remaining_hours"] == 140 and within["clock"]["overdue_hours"] is None
    breached = explain_sla(_app(), POLICY, TARGET, now=START + timedelta(hours=250))
    assert breached["clock"]["overdue_hours"] == 10 and breached["clock"]["remaining_hours"] is None
    assert "240 h" in breached["reason"]


def test_stage_block_uses_stage_entry_and_target():
    exp = explain_sla(_app(), POLICY, TARGET, now=START + timedelta(hours=40))
    s = exp["stage"]
    assert s["entered_at"] == (START + timedelta(hours=10)).isoformat()
    assert s["hours_in_stage"] == 30 and s["target_hours"] == 48 and s["warning_hours"] == 24
    assert s["status"] == "AT_RISK"


def test_completed():
    exp = explain_sla(_app(completed_at=(START + timedelta(hours=50)).isoformat()), POLICY, TARGET,
                      now=START + timedelta(hours=999))
    assert exp["state"] == "COMPLETED"
    assert exp["clock"]["elapsed_hours"] == 50


def test_no_policy_is_explained_not_assessed():
    exp = explain_sla(_app(), None, None, now=START + timedelta(hours=999))
    assert exp["state"] == "WITHIN_SLA"  # the calculation's default
    assert "not an assessment" in exp["reason"]
    assert exp["policy"] is None and exp["clock"]["due_at"] is None


def test_policy_never_presented_as_statutory_and_no_pause_invented():
    exp = explain_sla(_app(), POLICY, TARGET, now=START)
    assert exp["policy"]["is_verified_statutory_sla"] is False
    assert any("not verified statutory" in n for n in exp["notes"])
    assert any("pause/resume" in n for n in exp["notes"])


def test_synthetic_label():
    exp = explain_sla(_app(data_classification="SYNTHETIC_DEMO"), POLICY, TARGET, now=START)
    assert exp["is_synthetic"] and exp["notes"][0].startswith("SYNTHETIC DEMO DATA")


# --- API -------------------------------------------------------------------------

def test_api_explanation_matches_list_state(client):
    created = client.post("/api/v1/department/applications", json={
        "project_id": "freshbite", "requirement_id": "REQ-0001", "department_id": "dept-mpcb",
        "sla_policy_id": "sla-standard-30d"}).json()
    listed = next(a for a in client.get("/api/v1/department/applications").json()["items"]
                  if a["id"] == created["id"])
    exp = client.get(f"/api/v1/department/sla/applications/{created['id']}/explanation").json()
    assert exp["state"] == listed["sla"]["state"]
    assert exp["clock"]["due_at"] == listed["sla"]["due_at"]
    assert exp["policy"]["name"] == "Standard Review (30 days)"


def test_api_404_and_industry_forbidden(client, monkeypatch):
    assert client.get("/api/v1/department/sla/applications/nope/explanation").status_code == 404
    from app.main import app
    from app.security import CurrentUser, Role, get_current_user
    ind = CurrentUser(user_id="i", email="i@x", role=Role.INDUSTRY_USER, name="i", is_demo=False)
    app.dependency_overrides[get_current_user] = lambda: ind
    try:
        assert client.get("/api/v1/department/sla/applications/x/explanation").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
