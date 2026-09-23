"""
In-memory department store (MemoryDepartmentStore).

Mirrors the MemoryStore pattern: process-local dicts, no external dependencies.
Used when IRIS_DEMO_MODE=true and Supabase credentials are not set.
In production, get_department_store() instantiates SupabaseDepartmentStore
so all Government operational state is persisted in Supabase PostgreSQL.

SLA note (single authoritative calculation path)
-------------------------------------------------
Application-level SLA state is computed ONLY by ``_compute_sla_state()``.
Stage-level performance analytics use ``_compute_stage_durations()`` on
the stage_history data. These are two distinct but complementary metrics:
  - Application SLA state: total processing time vs sla_policy duration
  - Stage performance: per-stage dwell time vs sla_stage_targets
Both are computed in the backend. Neither is hardcoded.

Bottleneck methodology (deterministic)
----------------------------------------
Score formula: (avg_duration_hours * 0.40) + (backlog * 0.35) + (breach_pct * 100 * 0.25)
  - avg_duration_hours: mean of completed stage sojourns (from stage_history timestamps)
  - backlog: count of non-terminal applications in this stage
  - breach_pct: fraction of backlog with BREACHED overall SLA
Units: hours, application count, percent (0-100).
Operational heuristic only — not a statutory or legal regulatory metric.
Architecture is ready for NetworkX graph analysis in a future phase.

Department isolation:
---------------------
Every query and mutation accepts an optional ``department_id`` parameter.
When provided, results and actions are strictly scoped to that department.
"""
from __future__ import annotations

import copy
import logging
import statistics
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from ..department_schemas import ApplicationStage, SlaState, ALLOWED_TRANSITIONS

logger = logging.getLogger("iris.store.department")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _hours_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    """Return elapsed hours between two ISO timestamps, or None if either is missing."""
    s = _parse_dt(start)
    e = _parse_dt(end)
    if s and e:
        return (e - s).total_seconds() / 3600.0
    return None


# Demo SLA policies — clearly labelled as demo/configurable, not legal requirements
_SEED_SLA_POLICIES = [
    {
        "id": "sla-standard-30d",
        "name": "Standard Review (30 days)",
        "requirement_type": None,
        "duration_hours": 720,  # 30 days
        "warning_pct": 0.75,    # AT_RISK after 75% of 30 days (22.5 days)
        "description": "Demo configurable policy — 30-day review window with AT_RISK alert at day 22. "
                       "Not a legally mandated SLA; adjust duration_hours to match actual regulatory timelines.",
        "created_at": _now(),
        "updated_at": _now(),
    },
    {
        "id": "sla-fast-track-15d",
        "name": "Fast-Track Review (15 days)",
        "requirement_type": "food",
        "duration_hours": 360,  # 15 days
        "warning_pct": 0.80,
        "description": "Demo configurable policy for food-sector applications. "
                       "Replace with actual Maharashtra FSSAI processing timelines.",
        "created_at": _now(),
        "updated_at": _now(),
    },
    {
        "id": "sla-complex-60d",
        "name": "Complex Environmental Review (60 days)",
        "requirement_type": "environmental",
        "duration_hours": 1440,  # 60 days
        "warning_pct": 0.70,
        "description": "Demo configurable policy for complex environmental applications. "
                       "Replace with actual MoEFCC/MPCB timelines.",
        "created_at": _now(),
        "updated_at": _now(),
    },
]

# Demo SLA stage targets linked to the standard-30d policy
_SEED_SLA_STAGE_TARGETS = [
    {"policy_id": "sla-standard-30d", "stage": "SUBMITTED",             "target_hours": 48,  "warning_pct": 0.75, "description": "Demo: Acknowledge within 2 days"},
    {"policy_id": "sla-standard-30d", "stage": "UNDER_REVIEW",          "target_hours": 240, "warning_pct": 0.75, "description": "Demo: Initial review within 10 days"},
    {"policy_id": "sla-standard-30d", "stage": "INFORMATION_REQUESTED", "target_hours": 168, "warning_pct": 0.80, "description": "Demo: Response expected within 7 days"},
    {"policy_id": "sla-standard-30d", "stage": "INSPECTION_SCHEDULED",  "target_hours": 72,  "warning_pct": 0.70, "description": "Demo: Inspection within 3 days"},
    {"policy_id": "sla-standard-30d", "stage": "INSPECTION_COMPLETED",  "target_hours": 120, "warning_pct": 0.75, "description": "Demo: Report within 5 days"},
    {"policy_id": "sla-standard-30d", "stage": "RECOMMENDED",           "target_hours": 48,  "warning_pct": 0.75, "description": "Demo: Final decision within 2 days"},
]

# Demo departments
_SEED_DEPARTMENTS = [
    {
        "id": "dept-mpcb",
        "name": "Maharashtra Pollution Control Board",
        "code": "MPCB",
        "jurisdiction": "Maharashtra",
        "created_at": _now(),
    },
    {
        "id": "dept-fssai",
        "name": "Food Safety and Standards Authority",
        "code": "FSSAI",
        "jurisdiction": "Maharashtra",
        "created_at": _now(),
    },
]

# Demo government users
_SEED_DEPT_USERS = [
    {
        "id": "du-demo-manager",
        "department_id": "dept-mpcb",
        "user_id": "demo-officer-001",
        "supabase_auth_uid": None,
        "name": "Demo Officer",
        "email": "demo@iris.local",
        "role": "DEPARTMENT_ADMIN",
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    },
    {
        "id": "du-demo-officer",
        "department_id": "dept-mpcb",
        "user_id": "demo-officer-002",
        "supabase_auth_uid": None,
        "name": "Priya Sharma",
        "email": "priya.sharma@iris.local",
        "role": "DEPARTMENT_OFFICER",
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    },
]


# ---------------------------------------------------------------------------
# Single authoritative SLA calculation
# ---------------------------------------------------------------------------

def _compute_sla_state(
    policy: Optional[dict],
    started_at: Optional[str],
    completed_at: Optional[str],
    now: Optional[datetime] = None,
) -> dict:
    """
    Compute application-level SLA state from policy + timestamps.

    This is the SINGLE authoritative application SLA calculation.
    Called from every path that returns SLA state (list, detail, dashboard).

    Returns a dict with:
      - state: SlaState value
      - due_at: ISO string when SLA expires (None if no policy)
      - warning_at: ISO string when AT_RISK begins (None if no policy)
      - elapsed_pct: 0.0–1.0 of duration elapsed
    """
    if completed_at:
        return {
            "state": SlaState.COMPLETED,
            "due_at": None,
            "warning_at": None,
            "elapsed_pct": 1.0,
        }

    if not policy or not started_at:
        return {
            "state": SlaState.WITHIN_SLA,
            "due_at": None,
            "warning_at": None,
            "elapsed_pct": 0.0,
        }

    now = now or datetime.now(timezone.utc)
    start = _parse_dt(started_at)
    if not start:
        return {
            "state": SlaState.WITHIN_SLA,
            "due_at": None,
            "warning_at": None,
            "elapsed_pct": 0.0,
        }

    duration = timedelta(hours=policy["duration_hours"])
    due = start + duration
    warning = start + duration * policy["warning_pct"]

    elapsed = (now - start).total_seconds()
    total = duration.total_seconds()
    pct = min(elapsed / total, 1.0) if total > 0 else 0.0

    if now >= due:
        state = SlaState.BREACHED
    elif now >= warning:
        state = SlaState.AT_RISK
    else:
        state = SlaState.WITHIN_SLA

    return {
        "state": state,
        "due_at": due.isoformat(),
        "warning_at": warning.isoformat(),
        "elapsed_pct": round(pct, 4),
    }


def _compute_stage_sla_vs_target(
    stage: str,
    entered_at: Optional[str],
    now: Optional[datetime] = None,
    stage_target: Optional[dict] = None,
) -> Optional[str]:
    """
    Compare time in current stage vs sla_stage_target.
    Returns: "WITHIN", "AT_RISK", "EXCEEDED", or None if no target.
    """
    if not stage_target or not entered_at:
        return None
    now = now or datetime.now(timezone.utc)
    entered = _parse_dt(entered_at)
    if not entered:
        return None
    elapsed_h = (now - entered).total_seconds() / 3600.0
    target_h = stage_target["target_hours"]
    warning_h = target_h * stage_target["warning_pct"]
    if elapsed_h >= target_h:
        return "EXCEEDED"
    elif elapsed_h >= warning_h:
        return "AT_RISK"
    return "WITHIN"


def _compute_stage_durations(stage_history: list[dict]) -> dict[str, list[float]]:
    """
    Compute how long each application spent in each stage.
    Returns dict[stage → list of hours].
    Only includes COMPLETED stage sojourns (application has moved on).
    """
    if not stage_history:
        return {}

    sorted_history = sorted(stage_history, key=lambda h: h.get("created_at", ""))
    durations: dict[str, list[float]] = {}
    for i in range(len(sorted_history) - 1):
        current = sorted_history[i]
        next_entry = sorted_history[i + 1]
        stage = current.get("new_stage")
        if not stage:
            continue
        hours = _hours_between(current.get("created_at"), next_entry.get("created_at"))
        if hours is not None and hours >= 0:
            durations.setdefault(stage, []).append(hours)
    return durations


def _median(values: list[float]) -> Optional[float]:
    """Compute median of a list; returns None if empty."""
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    return sorted_vals[mid]


# Bottleneck score formula (documented operational heuristic)
_BOTTLENECK_W_DURATION = 0.40
_BOTTLENECK_W_BACKLOG = 0.35
_BOTTLENECK_W_BREACH = 0.25


def _bottleneck_score(avg_hours: Optional[float], backlog: int, breach_pct: float) -> float:
    return (
        (avg_hours or 0.0) * _BOTTLENECK_W_DURATION
        + backlog * _BOTTLENECK_W_BACKLOG
        + breach_pct * 100.0 * _BOTTLENECK_W_BREACH
    )


# ---------------------------------------------------------------------------
# DepartmentStore (In-memory implementation)
# ---------------------------------------------------------------------------

class DepartmentStore:
    def __init__(self) -> None:
        self._departments: dict[str, dict] = {d["id"]: copy.deepcopy(d) for d in _SEED_DEPARTMENTS}
        self._sla_policies: dict[str, dict] = {p["id"]: copy.deepcopy(p) for p in _SEED_SLA_POLICIES}
        self._sla_stage_targets: list[dict] = [copy.deepcopy(t) for t in _SEED_SLA_STAGE_TARGETS]
        self._applications: dict[str, dict] = {}
        self._stage_history: dict[str, list[dict]] = {}
        self._assignments: dict[str, list[dict]] = {}
        self._operational_events: dict[str, list[dict]] = {}
        self._sla_instances: dict[str, dict] = {}
        self._dept_users: dict[str, dict] = {u["id"]: copy.deepcopy(u) for u in _SEED_DEPT_USERS}
        self._user_profiles: dict[str, dict] = {}

    # -----------------------------------------------------------------------
    # Departments
    # -----------------------------------------------------------------------
    def list_departments(self) -> list[dict]:
        return [copy.deepcopy(d) for d in self._departments.values()]

    def get_department(self, dept_id: str) -> Optional[dict]:
        d = self._departments.get(dept_id)
        return copy.deepcopy(d) if d else None

    # -----------------------------------------------------------------------
    # SLA Policies
    # -----------------------------------------------------------------------
    def list_sla_policies(self) -> list[dict]:
        return [copy.deepcopy(p) for p in self._sla_policies.values()]

    def get_sla_policy(self, policy_id: str) -> Optional[dict]:
        p = self._sla_policies.get(policy_id)
        return copy.deepcopy(p) if p else None

    def create_sla_policy(self, policy: dict) -> dict:
        pid = policy.get("id") or str(uuid.uuid4())
        record = {**policy, "id": pid, "created_at": _now(), "updated_at": _now()}
        self._sla_policies[pid] = record
        return copy.deepcopy(record)

    # -----------------------------------------------------------------------
    # SLA Stage Targets
    # -----------------------------------------------------------------------
    def list_sla_stage_targets(self, policy_id: Optional[str] = None) -> list[dict]:
        targets = self._sla_stage_targets
        if policy_id:
            targets = [t for t in targets if t["policy_id"] == policy_id]
        return [copy.deepcopy(t) for t in targets]

    def create_sla_stage_target(self, data: dict) -> dict:
        tid = str(uuid.uuid4())
        record = {**data, "id": tid, "created_at": _now(), "updated_at": _now()}
        self._sla_stage_targets.append(record)
        return copy.deepcopy(record)

    def _get_stage_target(self, policy_id: str, stage: str) -> Optional[dict]:
        for t in self._sla_stage_targets:
            if t["policy_id"] == policy_id and t["stage"] == stage:
                return t
        return None

    # -----------------------------------------------------------------------
    # Applications (Department Scoped)
    # -----------------------------------------------------------------------
    def list_applications(
        self,
        department_id: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        requirement_id: Optional[str] = None,
        officer_id: Optional[str] = None,
        sla_state: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        project_id: Optional[str] = None,
    ) -> dict:
        apps = list(self._applications.values())

        # Department isolation check
        if department_id:
            apps = [a for a in apps if a.get("department_id") == department_id]
        if project_id:
            apps = [a for a in apps if a.get("project_id") == project_id]

        if search:
            q = search.lower()
            apps = [a for a in apps if
                    q in (a.get("title") or "").lower() or
                    q in (a.get("applicant_name") or "").lower() or
                    q in a.get("project_id", "").lower() or
                    q in a.get("application_id", "").lower()]
        if status:
            apps = [a for a in apps if a.get("current_stage") == status]
        if requirement_id:
            apps = [a for a in apps if a.get("requirement_id") == requirement_id]
        if officer_id:
            apps = [a for a in apps if a.get("assigned_officer_id") == officer_id]
        if date_from:
            apps = [a for a in apps if (a.get("created_at") or "") >= date_from]
        if date_to:
            apps = [a for a in apps if (a.get("created_at") or "") <= date_to]

        enriched = []
        for app in apps:
            a = copy.deepcopy(app)
            sla_instance = self._sla_instances.get(a["id"])
            policy = None
            if sla_instance:
                policy = self._sla_policies.get(sla_instance.get("policy_id", ""))
            sla_info = _compute_sla_state(
                policy,
                a.get("created_at"),
                a.get("completed_at"),
            )
            a["sla"] = sla_info
            enriched.append(a)

        if sla_state:
            enriched = [a for a in enriched if a["sla"]["state"] == sla_state]

        total = len(enriched)
        enriched.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        page = enriched[offset: offset + limit]

        return {"total": total, "items": page}

    def get_application(self, app_id: str, department_id: Optional[str] = None) -> Optional[dict]:
        app = self._applications.get(app_id)
        if not app:
            return None
        if department_id and app.get("department_id") != department_id:
            return None

        a = copy.deepcopy(app)
        sla_instance = self._sla_instances.get(app_id)
        policy = None
        if sla_instance:
            policy = self._sla_policies.get(sla_instance.get("policy_id", ""))
        a["sla"] = _compute_sla_state(
            policy, a.get("created_at"), a.get("completed_at")
        )
        a["sla_instance"] = copy.deepcopy(sla_instance) if sla_instance else None

        a["stage_history"] = copy.deepcopy(self._stage_history.get(app_id, []))
        a["assignment_history"] = copy.deepcopy(self._assignments.get(app_id, []))
        a["operational_events"] = copy.deepcopy(self._operational_events.get(app_id, []))

        return a

    def create_application(self, data: dict) -> dict:
        app_id = str(uuid.uuid4())
        n = len(self._applications) + 1
        application_number = f"APP-{n:05d}"

        record = {
            "id": app_id,
            "application_id": application_number,
            "project_id": data["project_id"],
            "requirement_id": data["requirement_id"],
            "department_id": data["department_id"],
            "title": data.get("title") or f"Application for {data['requirement_id']}",
            "applicant_name": data.get("applicant_name"),
            "current_stage": ApplicationStage.SUBMITTED.value,
            "assigned_officer_id": None,
            "assigned_officer_name": None,
            "created_at": _now(),
            "updated_at": _now(),
            "completed_at": None,
        }
        self._applications[app_id] = record
        self._stage_history[app_id] = [
            {
                "id": str(uuid.uuid4()),
                "application_id": app_id,
                "previous_stage": None,
                "new_stage": ApplicationStage.SUBMITTED.value,
                "actor": data.get("actor", "system"),
                "reason": "Application submitted",
                "created_at": _now(),
            }
        ]
        self._assignments[app_id] = []
        self._operational_events[app_id] = [
            {
                "id": str(uuid.uuid4()),
                "application_id": app_id,
                "event_type": "APPLICATION_SUBMITTED",
                "message": f"Application {application_number} submitted",
                "actor": data.get("actor", "system"),
                "created_at": _now(),
            }
        ]

        sla_policy_id = data.get("sla_policy_id") or "sla-standard-30d"
        self._sla_instances[app_id] = {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "policy_id": sla_policy_id,
            "started_at": _now(),
            "due_at": None,
            "completed_at": None,
        }

        return copy.deepcopy(record)

    def transition_stage(
        self,
        app_id: str,
        new_stage: str,
        actor: str,
        reason: Optional[str],
        department_id: Optional[str] = None,
    ) -> dict:
        app = self._applications.get(app_id)
        if not app or (department_id and app.get("department_id") != department_id):
            raise ValueError(f"Application {app_id} not found")

        current = ApplicationStage(app["current_stage"])
        next_stage = ApplicationStage(new_stage)

        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if next_stage not in allowed:
            raise ValueError(
                f"Invalid transition: {current.value} → {next_stage.value}. "
                f"Allowed from {current.value}: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        prev = app["current_stage"]
        app["current_stage"] = next_stage.value
        app["updated_at"] = _now()

        if next_stage in (ApplicationStage.APPROVED, ApplicationStage.REJECTED):
            app["completed_at"] = _now()
            if app_id in self._sla_instances:
                self._sla_instances[app_id]["completed_at"] = app["completed_at"]

        transition = {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "previous_stage": prev,
            "new_stage": next_stage.value,
            "actor": actor,
            "reason": reason,
            "created_at": _now(),
        }
        self._stage_history[app_id].append(transition)
        self._operational_events[app_id].append({
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "event_type": "STAGE_TRANSITION",
            "message": f"Stage changed from {prev} to {next_stage.value}" + (f": {reason}" if reason else ""),
            "actor": actor,
            "created_at": _now(),
        })

        return self.get_application(app_id, department_id=department_id)

    def assign_officer(
        self,
        app_id: str,
        officer_id: str,
        officer_name: str,
        actor: str,
        reason: Optional[str],
        department_id: Optional[str] = None,
    ) -> dict:
        app = self._applications.get(app_id)
        if not app or (department_id and app.get("department_id") != department_id):
            raise ValueError(f"Application {app_id} not found")

        # Officer must belong to the department
        if department_id:
            officer = self._dept_users.get(officer_id)
            if officer and officer.get("department_id") != department_id:
                raise ValueError(f"Officer {officer_id} does not belong to department {department_id}")

        prev_officer = app.get("assigned_officer_name")
        app["assigned_officer_id"] = officer_id
        app["assigned_officer_name"] = officer_name
        app["updated_at"] = _now()

        assignment = {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "officer_id": officer_id,
            "officer_name": officer_name,
            "assigned_by": actor,
            "reason": reason,
            "created_at": _now(),
        }
        self._assignments[app_id].append(assignment)
        self._operational_events[app_id].append({
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "event_type": "OFFICER_ASSIGNED" if not prev_officer else "OFFICER_REASSIGNED",
            "message": f"Assigned to {officer_name}" + (f" (was: {prev_officer})" if prev_officer else ""),
            "actor": actor,
            "created_at": _now(),
        })

        return self.get_application(app_id, department_id=department_id)

    # -----------------------------------------------------------------------
    # Dashboard & SLA Intelligence (Department Scoped)
    # -----------------------------------------------------------------------
    def get_dashboard_stats(self, department_id: Optional[str] = None) -> dict:
        apps = list(self._applications.values())
        if department_id:
            apps = [a for a in apps if a.get("department_id") == department_id]

        now = datetime.now(timezone.utc)

        total = len(apps)
        pending = sum(1 for a in apps if a["current_stage"] == ApplicationStage.SUBMITTED.value)
        in_progress = sum(1 for a in apps if a["current_stage"] not in (
            ApplicationStage.SUBMITTED.value, ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value
        ))
        completed = sum(1 for a in apps if a["current_stage"] in (
            ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value
        ))

        at_risk = 0
        breached = 0
        for app in apps:
            if app.get("completed_at"):
                continue
            instance = self._sla_instances.get(app["id"])
            policy = self._sla_policies.get(instance.get("policy_id", "")) if instance else None
            info = _compute_sla_state(policy, app.get("created_at"), app.get("completed_at"), now)
            if info["state"] == SlaState.AT_RISK.value:
                at_risk += 1
            elif info["state"] == SlaState.BREACHED.value:
                breached += 1

        pipeline = {stage.value: sum(1 for a in apps if a["current_stage"] == stage.value) for stage in ApplicationStage}

        sorted_apps = sorted(apps, key=lambda a: a.get("created_at", ""), reverse=True)
        recent = []
        for a in sorted_apps[:10]:
            instance = self._sla_instances.get(a["id"])
            policy = self._sla_policies.get(instance.get("policy_id", "")) if instance else None
            sla_info = _compute_sla_state(policy, a.get("created_at"), a.get("completed_at"), now)
            recent.append({
                "id": a["id"],
                "application_id": a.get("application_id"),
                "project_id": a.get("project_id"),
                "requirement_id": a.get("requirement_id"),
                "title": a.get("title"),
                "current_stage": a.get("current_stage"),
                "assigned_officer_name": a.get("assigned_officer_name"),
                "sla_state": sla_info["state"],
                "created_at": a.get("created_at"),
            })

        attention = []
        for a in apps:
            reasons = []
            if not a.get("assigned_officer_id"):
                reasons.append("Unassigned")
            if a["current_stage"] == ApplicationStage.INFORMATION_REQUESTED.value:
                reasons.append("Awaiting information")
            instance = self._sla_instances.get(a["id"])
            policy = self._sla_policies.get(instance.get("policy_id", "")) if instance else None
            sla_info = _compute_sla_state(policy, a.get("created_at"), a.get("completed_at"), now)
            if sla_info["state"] in (SlaState.AT_RISK.value, SlaState.BREACHED.value):
                reasons.append("SLA " + str(getattr(sla_info["state"], "value", sla_info["state"])).replace("_", " ").lower())
            if reasons:
                attention.append({
                    "id": a["id"],
                    "application_id": a.get("application_id"),
                    "title": a.get("title"),
                    "current_stage": a.get("current_stage"),
                    "reasons": reasons,
                    "sla_state": sla_info["state"],
                })

        return {
            "kpis": {
                "total": total,
                "pending": pending,
                "in_progress": in_progress,
                "completed": completed,
                "sla_at_risk": at_risk,
                "sla_breached": breached,
            },
            "pipeline": [{"stage": k, "count": v} for k, v in pipeline.items()],
            "recent_applications": recent,
            "attention_required": attention,
        }

    def get_timeline(self, app_id: str, department_id: Optional[str] = None) -> list[dict]:
        app = self._applications.get(app_id)
        if not app or (department_id and app.get("department_id") != department_id):
            raise ValueError(f"Application {app_id} not found")
        return copy.deepcopy(self._operational_events.get(app_id, []))

    def get_sla_dashboard(self, department_id: Optional[str] = None) -> dict:
        apps = list(self._applications.values())
        if department_id:
            apps = [a for a in apps if a.get("department_id") == department_id]

        now = datetime.now(timezone.utc)

        enriched = []
        for app in apps:
            instance = self._sla_instances.get(app["id"])
            policy = self._sla_policies.get(instance.get("policy_id", "")) if instance else None
            sla_info = _compute_sla_state(policy, app.get("created_at"), app.get("completed_at"), now)
            age_hours = _hours_between(app.get("created_at"), now.isoformat()) or 0.0

            enriched.append({
                "id": app["id"],
                "application_id": app.get("application_id"),
                "title": app.get("title"),
                "current_stage": app.get("current_stage"),
                "department_id": app.get("department_id"),
                "requirement_id": app.get("requirement_id"),
                "assigned_officer_name": app.get("assigned_officer_name"),
                "sla_state": sla_info["state"],
                "due_at": sla_info.get("due_at"),
                "warning_at": sla_info.get("warning_at"),
                "elapsed_pct": sla_info.get("elapsed_pct", 0.0),
                "age_hours": round(age_hours, 2),
                "created_at": app.get("created_at"),
                "completed_at": app.get("completed_at"),
            })

        within_sla = sum(1 for a in enriched if a["sla_state"] == SlaState.WITHIN_SLA.value)
        at_risk = sum(1 for a in enriched if a["sla_state"] == SlaState.AT_RISK.value)
        breached = sum(1 for a in enriched if a["sla_state"] == SlaState.BREACHED.value)
        completed_sla = sum(1 for a in enriched if a["sla_state"] == SlaState.COMPLETED.value)

        active = [a for a in enriched if not a["completed_at"]]
        aging_0_7 = sum(1 for a in active if a["age_hours"] < 168)
        aging_7_30 = sum(1 for a in active if 168 <= a["age_hours"] < 720)
        aging_30_60 = sum(1 for a in active if 720 <= a["age_hours"] < 1440)
        aging_over_60 = sum(1 for a in active if a["age_hours"] >= 1440)

        sla_order = {SlaState.BREACHED.value: 0, SlaState.AT_RISK.value: 1, SlaState.WITHIN_SLA.value: 2, SlaState.COMPLETED.value: 3}
        enriched.sort(key=lambda a: (sla_order.get(a["sla_state"], 9), -a["age_hours"]))

        stage_performance = self.get_sla_stage_performance(department_id=department_id)

        breach_by_stage: dict[str, int] = {}
        for a in enriched:
            if a["sla_state"] in (SlaState.BREACHED.value, SlaState.AT_RISK.value):
                stage = a["current_stage"]
                breach_by_stage[stage] = breach_by_stage.get(stage, 0) + 1

        return {
            "kpis": {
                "total": len(enriched),
                "active": len(active),
                "completed": completed_sla,
                "within_sla": within_sla,
                "at_risk": at_risk,
                "breached": breached,
                "aging_0_7d": aging_0_7,
                "aging_7_30d": aging_7_30,
                "aging_30_60d": aging_30_60,
                "aging_over_60d": aging_over_60,
            },
            "applications": enriched,
            "stage_performance": stage_performance,
            "breach_by_stage": [
                {"stage": k, "count": v}
                for k, v in sorted(breach_by_stage.items(), key=lambda x: -x[1])
            ],
        }

    def get_sla_stage_performance(self, department_id: Optional[str] = None) -> list[dict]:
        relevant_app_ids = {
            a["id"] for a in self._applications.values()
            if not department_id or a.get("department_id") == department_id
        }

        all_durations: dict[str, list[float]] = {}
        stage_entry_counts: dict[str, int] = {}
        stage_completed_counts: dict[str, int] = {}

        for app_id, history in self._stage_history.items():
            if app_id not in relevant_app_ids:
                continue
            durations = _compute_stage_durations(history)
            for stage, hours_list in durations.items():
                all_durations.setdefault(stage, []).extend(hours_list)

            sorted_h = sorted(history, key=lambda h: h.get("created_at", ""))
            for i, entry in enumerate(sorted_h):
                stage = entry.get("new_stage")
                if stage:
                    stage_entry_counts[stage] = stage_entry_counts.get(stage, 0) + 1
                    if i < len(sorted_h) - 1:
                        stage_completed_counts[stage] = stage_completed_counts.get(stage, 0) + 1

        results = []
        for stage_enum in ApplicationStage:
            st = stage_enum.value
            hours_list = all_durations.get(st, [])
            avg_h = statistics.mean(hours_list) if hours_list else None
            med_h = _median(hours_list)
            min_h = min(hours_list) if hours_list else None
            max_h = max(hours_list) if hours_list else None

            target = self._get_stage_target("sla-standard-30d", st)
            vs_target = None
            if target and avg_h is not None:
                target_h = target["target_hours"]
                warning_h = target_h * target["warning_pct"]
                if avg_h >= target_h:
                    vs_target = "EXCEEDED"
                elif avg_h >= warning_h:
                    vs_target = "AT_RISK"
                else:
                    vs_target = "WITHIN"

            results.append({
                "stage": st,
                "entry_count": stage_entry_counts.get(st, 0),
                "completed_count": stage_completed_counts.get(st, 0),
                "avg_duration_hours": round(avg_h, 2) if avg_h is not None else None,
                "median_duration_hours": round(med_h, 2) if med_h is not None else None,
                "min_duration_hours": round(min_h, 2) if min_h is not None else None,
                "max_duration_hours": round(max_h, 2) if max_h is not None else None,
                "target_hours": target["target_hours"] if target else None,
                "target_warning_pct": target["warning_pct"] if target else None,
                "vs_target": vs_target,
            })
        return results

    def get_sla_applications(
        self,
        department_id: Optional[str] = None,
        sla_state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        result = self.get_sla_dashboard(department_id=department_id)
        apps = result["applications"]
        if sla_state:
            apps = [a for a in apps if a["sla_state"] == sla_state]
        total = len(apps)
        return {"total": total, "items": apps[offset: offset + limit]}

    # -----------------------------------------------------------------------
    # Bottleneck Analytics (Department Scoped)
    # -----------------------------------------------------------------------
    def get_bottleneck_report(self, department_id: Optional[str] = None) -> dict:
        now = datetime.now(timezone.utc)
        apps = list(self._applications.values())
        if department_id:
            apps = [a for a in apps if a.get("department_id") == department_id]

        total_apps = len(apps)
        terminal = {ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value}
        active_apps = [a for a in apps if a["current_stage"] not in terminal]
        total_active = len(active_apps)

        backlog: dict[str, list[dict]] = {}
        for app in active_apps:
            stage = app["current_stage"]
            if hasattr(stage, 'value'):
                stage = stage.value
            backlog.setdefault(stage, []).append(app)

        def _app_sla_state(app: dict) -> str:
            instance = self._sla_instances.get(app["id"])
            policy = self._sla_policies.get(instance.get("policy_id", "")) if instance else None
            info = _compute_sla_state(policy, app.get("created_at"), app.get("completed_at"), now)
            return info["state"]

        relevant_app_ids = {a["id"] for a in apps}
        all_stage_durations: dict[str, list[float]] = {}
        app_stage_entry: dict[str, dict[str, str]] = {}

        for app_id, history in self._stage_history.items():
            if app_id not in relevant_app_ids:
                continue
            durations = _compute_stage_durations(history)
            for stage, hours_list in durations.items():
                all_stage_durations.setdefault(stage, []).extend(hours_list)

            sorted_h = sorted(history, key=lambda h: h.get("created_at", ""))
            if sorted_h:
                last = sorted_h[-1]
                app_stage_entry[app_id] = {last.get("new_stage", ""): last.get("created_at", "")}

        seven_days_ago = (now - timedelta(days=7)).isoformat()
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        throughput_7d: dict[str, int] = {}
        throughput_30d: dict[str, int] = {}

        for app_id, history in self._stage_history.items():
            if app_id not in relevant_app_ids:
                continue
            sorted_h = sorted(history, key=lambda h: h.get("created_at", ""))
            for i in range(1, len(sorted_h)):
                exit_entry = sorted_h[i]
                prev_stage = exit_entry.get("previous_stage")
                exit_time = exit_entry.get("created_at", "")
                if prev_stage:
                    if exit_time >= seven_days_ago:
                        throughput_7d[prev_stage] = throughput_7d.get(prev_stage, 0) + 1
                    if exit_time >= thirty_days_ago:
                        throughput_30d[prev_stage] = throughput_30d.get(prev_stage, 0) + 1

        stage_metrics = []
        for stage_enum in ApplicationStage:
            stage = stage_enum.value
            if stage in terminal:
                continue

            stage_apps = backlog.get(stage, [])
            stage_backlog = len(stage_apps)

            sla_states = [_app_sla_state(a) for a in stage_apps]
            at_risk_count = sum(1 for s in sla_states if s == SlaState.AT_RISK.value)
            breached_count = sum(1 for s in sla_states if s == SlaState.BREACHED.value)
            breach_pct = breached_count / stage_backlog if stage_backlog > 0 else 0.0

            dur_list = all_stage_durations.get(stage, [])
            avg_h = statistics.mean(dur_list) if dur_list else None
            med_h = _median(dur_list)
            min_h = min(dur_list) if dur_list else None
            max_h = max(dur_list) if dur_list else None
            entry_count = sum(
                1 for app_id, history in self._stage_history.items()
                if app_id in relevant_app_ids
                for entry in history if entry.get("new_stage") == stage
            )

            aging_7d = 0
            aging_14d = 0
            aging_30d = 0
            for app in stage_apps:
                app_id = app["id"]
                entry_info = app_stage_entry.get(app_id, {})
                entered_at = entry_info.get(stage)
                if entered_at:
                    h = _hours_between(entered_at, now.isoformat()) or 0.0
                    if h >= 720:
                        aging_30d += 1
                    if h >= 336:
                        aging_14d += 1
                    if h >= 168:
                        aging_7d += 1

            score = _bottleneck_score(avg_h, stage_backlog, breach_pct)
            stage_metrics.append({
                "stage": stage,
                "backlog": stage_backlog,
                "avg_duration_hours": round(avg_h, 2) if avg_h is not None else None,
                "median_duration_hours": round(med_h, 2) if med_h is not None else None,
                "min_duration_hours": round(min_h, 2) if min_h is not None else None,
                "max_duration_hours": round(max_h, 2) if max_h is not None else None,
                "entry_count": entry_count,
                "completed_count": len(dur_list),
                "at_risk_count": at_risk_count,
                "breached_count": breached_count,
                "sla_breach_pct": round(breach_pct, 4),
                "bottleneck_score": round(score, 4),
                "rank": 0,
                "aging_7d": aging_7d,
                "aging_14d": aging_14d,
                "aging_30d": aging_30d,
                "throughput_7d": throughput_7d.get(stage, 0),
                "throughput_30d": throughput_30d.get(stage, 0),
            })

        stage_metrics.sort(key=lambda m: -m["bottleneck_score"])
        for i, m in enumerate(stage_metrics):
            m["rank"] = i + 1

        officer_workload = self._get_officer_workload(now, department_id=department_id)
        top_stage = stage_metrics[0]["stage"] if stage_metrics else None
        top_score = stage_metrics[0]["bottleneck_score"] if stage_metrics else None

        return {
            "generated_at": now.isoformat(),
            "total_active": total_active,
            "total_applications": total_apps,
            "methodology": (
                "Deterministic operational heuristic. Computed from real stage_history timestamps + sla_instances. "
                "No fabricated data. Bottleneck score = "
                f"(avg_duration_hours × {_BOTTLENECK_W_DURATION}) + "
                f"(backlog × {_BOTTLENECK_W_BACKLOG}) + "
                f"(breach_pct × 100 × {_BOTTLENECK_W_BREACH}). "
                "Units: duration in hours, backlog in application count, breach in percent. "
                "Heuristic metric only — not statutory. "
                "Architecture ready for NetworkX graph analysis in a future phase."
            ),
            "stages": stage_metrics,
            "officers": officer_workload,
            "top_bottleneck_stage": top_stage,
            "top_bottleneck_score": top_score,
        }

    def get_bottleneck_stages(self, department_id: Optional[str] = None) -> list[dict]:
        return self.get_bottleneck_report(department_id=department_id)["stages"]

    def get_bottleneck_officers(self, department_id: Optional[str] = None) -> list[dict]:
        now = datetime.now(timezone.utc)
        return self._get_officer_workload(now, department_id=department_id)

    def get_bottleneck_trends(self, days: int = 14, department_id: Optional[str] = None) -> list[dict]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        relevant_app_ids = {
            a["id"] for a in self._applications.values()
            if not department_id or a.get("department_id") == department_id
        }

        trends: dict[str, dict[str, dict[str, int]]] = {}
        for app_id, history in self._stage_history.items():
            if app_id not in relevant_app_ids:
                continue
            sorted_h = sorted(history, key=lambda h: h.get("created_at", ""))
            for i, entry in enumerate(sorted_h):
                ts = entry.get("created_at", "")
                if ts < cutoff_iso:
                    continue
                date = ts[:10]
                stage = entry.get("new_stage")
                if not stage:
                    continue
                trends.setdefault(date, {}).setdefault(stage, {"entered": 0, "exited": 0})
                trends[date][stage]["entered"] += 1
                if i > 0:
                    prev_stage = sorted_h[i - 1].get("new_stage")
                    if prev_stage:
                        trends.setdefault(date, {}).setdefault(prev_stage, {"entered": 0, "exited": 0})
                        trends[date][prev_stage]["exited"] += 1

        result = []
        for date in sorted(trends.keys()):
            for stage, counts in trends[date].items():
                result.append({
                    "date": date,
                    "stage": stage,
                    "entered": counts["entered"],
                    "exited": counts["exited"],
                })
        return result

    def _get_officer_workload(self, now: Optional[datetime] = None, department_id: Optional[str] = None) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        terminal = {ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value}

        apps = list(self._applications.values())
        if department_id:
            apps = [a for a in apps if a.get("department_id") == department_id]

        officer_counts: dict[str, dict] = {}
        for app in apps:
            oid = app.get("assigned_officer_id")
            if not oid:
                continue
            if oid not in officer_counts:
                officer_counts[oid] = {
                    "officer_id": oid,
                    "officer_name": app.get("assigned_officer_name", oid),
                    "active": 0,
                    "completed": 0,
                    "at_risk": 0,
                    "breached": 0,
                }
            stage = app.get("current_stage")
            if hasattr(stage, 'value'):
                stage = stage.value
            if stage in terminal:
                officer_counts[oid]["completed"] += 1
            else:
                officer_counts[oid]["active"] += 1
                instance = self._sla_instances.get(app["id"])
                policy = self._sla_policies.get(instance.get("policy_id", "")) if instance else None
                info = _compute_sla_state(policy, app.get("created_at"), app.get("completed_at"), now)
                if info["state"] == SlaState.AT_RISK.value:
                    officer_counts[oid]["at_risk"] += 1
                elif info["state"] == SlaState.BREACHED.value:
                    officer_counts[oid]["breached"] += 1

        result = []
        for oid, data in officer_counts.items():
            result.append({
                "officer_id": data["officer_id"],
                "officer_name": data["officer_name"],
                "department_id": department_id,
                "role": "DEPARTMENT_OFFICER",
                "is_active": True,
                "active_applications": data["active"],
                "completed_applications": data["completed"],
                "total_applications": data["active"] + data["completed"],
                "at_risk_count": data["at_risk"],
                "breached_count": data["breached"],
            })
        result.sort(key=lambda x: -x["active_applications"])
        return result

    # -----------------------------------------------------------------------
    # User Profile Management
    # -----------------------------------------------------------------------
    def get_user_profile_by_auth_uid(self, supabase_auth_uid: str) -> Optional[dict]:
        for profile in self._user_profiles.values():
            if profile.get("supabase_auth_uid") == supabase_auth_uid:
                p = copy.deepcopy(profile)
                if p.get("department_id"):
                    dept = self._departments.get(p["department_id"])
                    p["department_name"] = dept["name"] if dept else None
                return p
        for du in self._dept_users.values():
            if du.get("supabase_auth_uid") == supabase_auth_uid:
                role = du.get("role", "DEPARTMENT_OFFICER")
                dept = self._departments.get(du.get("department_id", ""))
                return {
                    "id": du["id"],
                    "supabase_auth_uid": supabase_auth_uid,
                    "email": du.get("email"),
                    "full_name": du.get("name"),
                    "iris_role": role,
                    "department_id": du.get("department_id"),
                    "department_name": dept["name"] if dept else None,
                    "is_active": du.get("is_active", True),
                    "pending_government_link": False,
                }
        return None

    def create_or_update_user_profile(self, data: dict) -> dict:
        auth_uid = data.get("supabase_auth_uid")
        if not auth_uid:
            raise ValueError("supabase_auth_uid is required")

        existing_id = None
        for pid, profile in self._user_profiles.items():
            if profile.get("supabase_auth_uid") == auth_uid:
                existing_id = pid
                break

        if existing_id:
            profile = self._user_profiles[existing_id]
            for field in ("email", "full_name", "avatar_url", "provider"):
                if field in data:
                    profile[field] = data[field]
            profile["updated_at"] = _now()
            return copy.deepcopy(profile)

        profile_id = str(uuid.uuid4())
        profile = {
            "id": profile_id,
            "supabase_auth_uid": auth_uid,
            "email": data.get("email"),
            "full_name": data.get("full_name"),
            "avatar_url": data.get("avatar_url"),
            "iris_role": "INDUSTRY_USER",
            "department_id": None,
            "is_active": True,
            "pending_government_link": False,
            "provider": data.get("provider", "email"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._user_profiles[profile_id] = profile
        return copy.deepcopy(profile)

    def list_user_profiles(
        self,
        iris_role: Optional[str] = None,
        pending_only: bool = False,
    ) -> list[dict]:
        profiles = list(self._user_profiles.values())
        if iris_role:
            profiles = [p for p in profiles if p.get("iris_role") == iris_role]
        if pending_only:
            profiles = [p for p in profiles if p.get("pending_government_link")]
        result = []
        for p in profiles:
            pd = copy.deepcopy(p)
            if pd.get("department_id"):
                dept = self._departments.get(pd["department_id"])
                pd["department_name"] = dept["name"] if dept else None
            else:
                pd["department_name"] = None
            result.append(pd)
        result.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return result

    def link_user_to_department(
        self,
        profile_id: str,
        department_id: str,
        role: str,
        name: Optional[str] = None,
    ) -> dict:
        profile = self._user_profiles.get(profile_id)
        if not profile:
            raise ValueError(f"User profile {profile_id} not found")

        valid_roles = {"DEPARTMENT_OFFICER", "DEPARTMENT_MANAGER", "DEPARTMENT_ADMIN"}
        if role not in valid_roles:
            raise ValueError(f"Invalid government role: {role}. Must be one of {valid_roles}")

        if department_id not in self._departments:
            raise ValueError(f"Department {department_id} not found")

        profile["iris_role"] = role
        profile["department_id"] = department_id
        profile["pending_government_link"] = False
        profile["updated_at"] = _now()

        auth_uid = profile.get("supabase_auth_uid")
        du_id = str(uuid.uuid4())
        display_name = name or profile.get("full_name") or profile.get("email") or auth_uid

        existing_du = None
        for du in self._dept_users.values():
            if auth_uid and du.get("supabase_auth_uid") == auth_uid:
                existing_du = du
                break

        if existing_du:
            existing_du["role"] = role
            existing_du["department_id"] = department_id
            existing_du["name"] = display_name
            existing_du["is_active"] = True
            existing_du["updated_at"] = _now()
        else:
            new_du = {
                "id": du_id,
                "department_id": department_id,
                "user_id": auth_uid,
                "supabase_auth_uid": auth_uid,
                "name": display_name,
                "email": profile.get("email"),
                "role": role,
                "is_active": True,
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._dept_users[du_id] = new_du

        dept = self._departments.get(department_id)
        result = copy.deepcopy(profile)
        result["department_name"] = dept["name"] if dept else None
        return result

    def update_department_user(self, dept_user_id: str, data: dict, department_id: Optional[str] = None) -> dict:
        du = self._dept_users.get(dept_user_id)
        if not du or (department_id and du.get("department_id") != department_id):
            raise ValueError(f"Department user {dept_user_id} not found")
        if "role" in data:
            du["role"] = data["role"]
        if "is_active" in data:
            du["is_active"] = data["is_active"]
        if "department_id" in data:
            du["department_id"] = data["department_id"]
        du["updated_at"] = _now()

        auth_uid = du.get("supabase_auth_uid")
        if auth_uid:
            for profile in self._user_profiles.values():
                if profile.get("supabase_auth_uid") == auth_uid:
                    if "role" in data:
                        profile["iris_role"] = data["role"]
                    if "department_id" in data:
                        profile["department_id"] = data["department_id"]
                    profile["updated_at"] = _now()
                    break

        return copy.deepcopy(du)

    def list_department_users(self, department_id: Optional[str] = None) -> list[dict]:
        users = list(self._dept_users.values())
        if department_id:
            users = [u for u in users if u.get("department_id") == department_id]
        result = []
        for u in users:
            ud = copy.deepcopy(u)
            dept = self._departments.get(ud.get("department_id", ""))
            ud["department_name"] = dept["name"] if dept else None
            result.append(ud)
        result.sort(key=lambda u: u.get("created_at", ""), reverse=True)
        return result

    def get_department_user(self, dept_user_id: str, department_id: Optional[str] = None) -> Optional[dict]:
        du = self._dept_users.get(dept_user_id)
        if not du or (department_id and du.get("department_id") != department_id):
            return None
        ud = copy.deepcopy(du)
        dept = self._departments.get(ud.get("department_id", ""))
        ud["department_name"] = dept["name"] if dept else None
        return ud

    def create_department_user(self, data: dict) -> dict:
        du_id = str(uuid.uuid4())
        record = {
            "id": du_id,
            "department_id": data["department_id"],
            "user_id": None,
            "supabase_auth_uid": None,
            "name": data["name"],
            "email": data.get("email"),
            "role": data.get("role", "DEPARTMENT_OFFICER"),
            "is_active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._dept_users[du_id] = record
        return copy.deepcopy(record)


# Singleton for the in-process store (used in demo mode / testing)
_dept_store: Optional[DepartmentStore] = None


def get_department_store():
    """
    Factory function for the Government operational store.
    - If Supabase is configured: returns SupabaseDepartmentStore (PostgREST persistence).
    - If not configured and IRIS_DEMO_MODE=true: returns in-memory DepartmentStore.
    - If not configured and IRIS_DEMO_MODE=false: raises StoreError (fails closed in production).
    """
    from ..config import get_settings
    from .base import StoreError
    settings = get_settings()

    if settings.supabase_configured:
        from .supabase_department_store import SupabaseDepartmentStore
        return SupabaseDepartmentStore(
            url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            schema=settings.supabase_schema,
        )

    if not settings.iris_demo_mode:
        raise StoreError(
            "Supabase persistence is not configured and IRIS_DEMO_MODE is false. "
            "Government operational store cannot initialize in production without persistence."
        )

    global _dept_store
    if _dept_store is None:
        _dept_store = DepartmentStore()
    return _dept_store
