"""
Tests for SLA calculation consistency.

Verifies boundary consistency between:
  1. The Python single authoritative calculation: ``_compute_sla_state()``
  2. The SQL view specification: ``public.v_application_sla_status`` (0003_auth_sla_bottlenecks.sql)

Both must produce identical state transitions:
  - When completed_at is set -> COMPLETED
  - When elapsed < warning_pct -> WITHIN_SLA
  - When elapsed >= warning_pct and < 100% -> AT_RISK
  - When elapsed >= 100% -> BREACHED
"""
from datetime import datetime, timezone, timedelta
import pytest

from app.store.department_store import _compute_sla_state
from app.department_schemas import SlaState


def simulate_sql_view_case(
    completed_at: str | None,
    started_at: str | None,
    duration_hours: int | None,
    warning_pct: float | None,
    now: datetime,
) -> str:
    """
    Exact simulation of SQL CASE expression from v_application_sla_status:

    CASE
      WHEN a.completed_at IS NOT NULL THEN 'COMPLETED'
      WHEN si.id IS NULL OR sp.id IS NULL THEN 'WITHIN_SLA'
      WHEN now() >= si.started_at + (sp.duration_hours * INTERVAL '1 hour')
        THEN 'BREACHED'
      WHEN now() >= si.started_at + (sp.duration_hours * sp.warning_pct * INTERVAL '1 hour')
        THEN 'AT_RISK'
      ELSE 'WITHIN_SLA'
    END AS sla_state
    """
    if completed_at is not None:
        return "COMPLETED"
    if started_at is None or duration_hours is None or warning_pct is None:
        return "WITHIN_SLA"

    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    due_dt = start_dt + timedelta(hours=duration_hours)
    warning_dt = start_dt + timedelta(hours=duration_hours * warning_pct)

    if now >= due_dt:
        return "BREACHED"
    if now >= warning_dt:
        return "AT_RISK"
    return "WITHIN_SLA"


# Test policy: 100 hours, warning at 75% (75 hours)
POLICY = {
    "duration_hours": 100,
    "warning_pct": 0.75,
}

BASE_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
BASE_START_ISO = BASE_START.isoformat()


@pytest.mark.parametrize(
    "elapsed_hours, expected_state",
    [
        (0.0, "WITHIN_SLA"),
        (10.0, "WITHIN_SLA"),
        (50.0, "WITHIN_SLA"),
        (74.99, "WITHIN_SLA"),      # just before warning boundary
        (75.0, "AT_RISK"),          # exactly at warning boundary
        (75.01, "AT_RISK"),         # just past warning boundary
        (85.0, "AT_RISK"),
        (99.99, "AT_RISK"),         # just before due date
        (100.0, "BREACHED"),        # exactly at due boundary
        (100.01, "BREACHED"),       # just past due boundary
        (150.0, "BREACHED"),
    ],
)
def test_sla_boundary_consistency_with_sql_view(elapsed_hours, expected_state):
    """
    Verify Python calculation matches SQL view output at critical time boundaries.
    """
    current_time = BASE_START + timedelta(hours=elapsed_hours)

    # 1. Python calculation
    py_res = _compute_sla_state(
        started_at=BASE_START_ISO,
        completed_at=None,
        policy=POLICY,
        now=current_time,
    )

    # 2. Simulated SQL view calculation
    sql_res = simulate_sql_view_case(
        completed_at=None,
        started_at=BASE_START_ISO,
        duration_hours=POLICY["duration_hours"],
        warning_pct=POLICY["warning_pct"],
        now=current_time,
    )

    assert py_res["state"].value == expected_state
    assert sql_res == expected_state
    assert py_res["state"].value == sql_res


def test_completed_application_always_completed():
    """When completed_at is set, both Python and SQL must yield COMPLETED even if long overdue."""
    now = BASE_START + timedelta(hours=500)
    completed_time = (BASE_START + timedelta(hours=50)).isoformat()

    py_res = _compute_sla_state(
        started_at=BASE_START_ISO,
        completed_at=completed_time,
        policy=POLICY,
        now=now,
    )
    sql_res = simulate_sql_view_case(
        completed_at=completed_time,
        started_at=BASE_START_ISO,
        duration_hours=POLICY["duration_hours"],
        warning_pct=POLICY["warning_pct"],
        now=now,
    )

    assert py_res["state"] == SlaState.COMPLETED
    assert sql_res == "COMPLETED"


def test_missing_policy_defaults_to_within_sla():
    """Applications without SLA policy or start date default safely to WITHIN_SLA."""
    py_res = _compute_sla_state(
        started_at=None,
        completed_at=None,
        policy=None,
    )
    sql_res = simulate_sql_view_case(
        completed_at=None,
        started_at=None,
        duration_hours=None,
        warning_pct=None,
        now=datetime.now(timezone.utc),
    )

    assert py_res["state"] == SlaState.WITHIN_SLA
    assert sql_res == "WITHIN_SLA"
