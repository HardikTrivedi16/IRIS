"""
Grievance preparation / tracking / hand-off (P1-H).

Positioning: IRIS helps an applicant PREPARE a grievance about how one of
their applications is being handled, attaches the facts IRIS already holds
(application, current stage, SLA state), tracks it, and lets the responsible
department acknowledge, assign and resolve it. It is NOT a statutory
grievance mechanism and does not replace MAITRI / NSWS or any departmental
grievance portal. Nothing is ever filed automatically: creation requires an
explicit submission that acknowledges this.

Categories are IRIS tracking labels, not statutory grievance classes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

CATEGORIES = {
    "PROCESSING_DELAY": "Processing delay",
    "INFORMATION_REQUEST_UNCLEAR": "Information request unclear",
    "DOCUMENT_HANDLING": "Document handling",
    "OTHER": "Other",
}

OPEN = "OPEN"
ASSIGNED = "ASSIGNED"
UNDER_REVIEW = "UNDER_REVIEW"
RESOLVED = "RESOLVED"
CLOSED = "CLOSED"
STATUSES = (OPEN, ASSIGNED, UNDER_REVIEW, RESOLVED, CLOSED)

#: Government-side transitions. Assignment (OPEN -> ASSIGNED) goes through
#: the dedicated assign action so an officer is always recorded.
TRANSITIONS: dict[str, set[str]] = {
    OPEN: {UNDER_REVIEW},
    ASSIGNED: {UNDER_REVIEW},
    UNDER_REVIEW: {RESOLVED},
    RESOLVED: {CLOSED, UNDER_REVIEW},  # close, or reopen for more work
    CLOSED: set(),
}

DISCLAIMER = (
    "IRIS grievance tracking prepares and hands off your grievance with the "
    "application context attached. It is not a statutory grievance filing and "
    "does not replace MAITRI / NSWS or the department's own grievance mechanism."
)


class GrievanceRuleError(Exception):
    """A requested change is not allowed by the workflow."""


def check_transition(current: str, target: str, note: Optional[str]) -> None:
    if target not in STATUSES:
        raise GrievanceRuleError(f"Unknown status {target!r}.")
    if target not in TRANSITIONS.get(current, set()):
        allowed = ", ".join(sorted(TRANSITIONS.get(current, set()))) or "none"
        raise GrievanceRuleError(
            f"Cannot move a grievance from {current} to {target}. Allowed: {allowed}."
        )
    if target == RESOLVED and (not note or len(note.strip()) < 10):
        raise GrievanceRuleError("A resolution note of at least 10 characters is required to resolve.")


def build_context_snapshot(application: dict, now: Optional[datetime] = None) -> dict:
    """Copy — at filing time — the application facts IRIS already holds. The
    SLA block is the value the department store computed with the single
    authoritative SLA function; nothing is recomputed or estimated here."""
    now = now or datetime.now(timezone.utc)
    current_stage = application.get("current_stage")
    entered = None
    for h in application.get("stage_history") or []:
        if h.get("new_stage") == current_stage:
            entered = h.get("created_at") or entered
    sla = dict(application.get("sla") or {})
    return {
        "captured_at": now.isoformat(),
        "application_uuid": application.get("id"),
        "application_number": application.get("application_id"),
        "requirement_id": application.get("requirement_id"),
        "title": application.get("title"),
        "department_id": application.get("department_id"),
        "current_stage": current_stage,
        "current_stage_entered_at": entered,
        "application_created_at": application.get("created_at"),
        "sla": {
            "state": sla.get("state"),
            "due_at": sla.get("due_at"),
            "warning_at": sla.get("warning_at"),
            "elapsed_pct": sla.get("elapsed_pct"),
        },
        "data_classification": application.get("data_classification"),
    }


def applicant_view(application: dict) -> dict:
    """What an applicant may see about their own application: no officer
    identities or internal notes, just stage and SLA timing."""
    sla = application.get("sla") or {}
    return {
        "id": application.get("id"),
        "application_id": application.get("application_id"),
        "requirement_id": application.get("requirement_id"),
        "title": application.get("title"),
        "department_id": application.get("department_id"),
        "current_stage": application.get("current_stage"),
        "created_at": application.get("created_at"),
        "completed_at": application.get("completed_at"),
        "sla": {k: sla.get(k) for k in ("state", "due_at", "warning_at", "elapsed_pct")},
        "data_classification": application.get("data_classification"),
    }
