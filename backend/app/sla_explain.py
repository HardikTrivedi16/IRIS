"""
"Why this SLA status?" (P1-I).

Explains an application's SLA state using ONLY the existing deterministic
timing data: the application's timestamps, its SLA policy and stage target on
record, and the single authoritative calculation in
``department_store._compute_sla_state`` / ``_compute_stage_sla_vs_target``.
Both are called here with one fixed ``now`` so every number shown is
consistent with the state shown. Nothing is predicted.

Honesty notes surfaced with every explanation:
* SLA policies in IRIS are configured operational targets. IRIS holds no
  verified statutory SLA data, so a policy is never presented as law.
* The clock runs continuously from application creation. IRIS does not model
  pause/resume (for example while information is requested) because no such
  rule is recorded — it does not invent one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .store.department_store import (
    _compute_sla_state,
    _compute_stage_sla_vs_target,
    _parse_dt,
)

_H = 3600.0


def _state_value(state) -> str:
    return state.value if hasattr(state, "value") else str(state)


def _hours(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / _H, 2)


def explain_sla(
    application: dict,
    policy: Optional[dict],
    stage_target: Optional[dict],
    now: Optional[datetime] = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    started_at = application.get("created_at")
    completed_at = application.get("completed_at")

    computed = _compute_sla_state(policy, started_at, completed_at, now=now)
    state = _state_value(computed["state"])

    start = _parse_dt(started_at)
    due = _parse_dt(computed.get("due_at"))
    warn = _parse_dt(computed.get("warning_at"))

    clock = {
        "started_at": started_at,
        "evaluated_at": now.isoformat(),
        "completed_at": completed_at,
        "elapsed_hours": _hours(start, _parse_dt(completed_at) or now) if start else None,
        "due_at": computed.get("due_at"),
        "warning_at": computed.get("warning_at"),
        "remaining_hours": _hours(now, due) if due and state in ("WITHIN_SLA", "AT_RISK") else None,
        "overdue_hours": _hours(due, now) if due and state == "BREACHED" else None,
        "elapsed_pct": computed.get("elapsed_pct"),
    }

    if state == "COMPLETED":
        reason = "The application has a completion time recorded, so its SLA clock has stopped."
    elif policy is None or not start:
        reason = ("No SLA policy (or no start time) is attached to this application, so no due "
                  "date exists. The calculation reports WITHIN_SLA by default — this is not an "
                  "assessment of timeliness.")
    elif state == "BREACHED":
        reason = (f"Now is at or after the due time: start + {policy['duration_hours']} h "
                  f"= {computed['due_at']}.")
    elif state == "AT_RISK":
        reason = (f"Now is past the warning point ({policy['warning_pct']:.0%} of "
                  f"{policy['duration_hours']} h) but before the due time.")
    else:
        reason = (f"Now is before the warning point ({policy['warning_pct']:.0%} of "
                  f"{policy['duration_hours']} h after start).")

    current_stage = application.get("current_stage")
    entered_at = None
    for h in application.get("stage_history") or []:
        if h.get("new_stage") == current_stage:
            entered_at = h.get("created_at") or entered_at
    entered_at = entered_at or started_at
    entered = _parse_dt(entered_at)
    stage_status = _compute_stage_sla_vs_target(current_stage, entered_at, now=now, stage_target=stage_target)
    stage = {
        "current_stage": current_stage,
        "entered_at": entered_at,
        "hours_in_stage": _hours(entered, now) if entered and not completed_at else None,
        "target_hours": (stage_target or {}).get("target_hours"),
        "warning_hours": round(stage_target["target_hours"] * stage_target["warning_pct"], 2)
        if stage_target else None,
        "status": stage_status,
        "target_description": (stage_target or {}).get("description"),
    }

    classification = application.get("data_classification")
    notes = [
        "SLA policies in IRIS are configured operational targets, not verified statutory "
        "timelines.",
        "The clock runs continuously from application creation; IRIS does not model "
        "pause/resume because no such rule is recorded.",
    ]
    if classification == "SYNTHETIC_DEMO":
        notes.insert(0, "SYNTHETIC DEMO DATA — this application and its timestamps come from a synthetic seed.")
    elif classification is None:
        notes.append("Data provenance is not recorded for this application (Supabase records are classified once migration 0007 is applied).")

    return {
        "application": {
            "id": application.get("id"),
            "application_id": application.get("application_id"),
            "title": application.get("title"),
            "requirement_id": application.get("requirement_id"),
        },
        "state": state,
        "reason": reason,
        "clock": clock,
        "policy": {
            "id": policy.get("id"),
            "name": policy.get("name"),
            "duration_hours": policy.get("duration_hours"),
            "warning_pct": policy.get("warning_pct"),
            "description": policy.get("description"),
            "is_verified_statutory_sla": False,
        } if policy else None,
        "stage": stage,
        "data_classification": classification,
        "is_synthetic": classification == "SYNTHETIC_DEMO",
        "notes": notes,
    }
