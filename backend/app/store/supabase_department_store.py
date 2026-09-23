"""
Supabase-backed department store implementation.

Persists all Government portal operational state into Supabase PostgreSQL:
  - departments
  - department_users
  - sla_policies
  - sla_stage_targets
  - applications
  - application_stage_history
  - assignment_history
  - sla_instances
  - operational_events
  - user_profiles

SLA calculation note (single authoritative path):
  Uses the authoritative ``_compute_sla_state()`` function from department_store.py
  to compute SLA states dynamically over persisted timestamps, guaranteeing
  100% consistency with the SQL view logic in v_application_sla_status.

Department isolation note:
  Every query and mutation enforces department_id scoping. An officer or admin
  belonging to department A cannot view or alter applications, SLAs, bottlenecks,
  or officer records of department B.
"""
from __future__ import annotations

import copy
import logging
import statistics
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx

from .base import StoreError
from .department_store import (
    _compute_sla_state,
    _compute_stage_durations,
    _median,
    _hours_between,
    _now,
    _parse_dt,
    _bottleneck_score,
    _BOTTLENECK_W_DURATION,
    _BOTTLENECK_W_BACKLOG,
    _BOTTLENECK_W_BREACH,
)
from ..department_schemas import ApplicationStage, SlaState, ALLOWED_TRANSITIONS
from ..legacy_evidence import legacy_operational_info

logger = logging.getLogger("iris.store.supabase_department")

_SLA_REASON = {SlaState.AT_RISK.value: "SLA at risk", SlaState.BREACHED.value: "SLA breached"}


class SupabaseDepartmentStore:
    def __init__(
        self,
        url: str,
        service_role_key: str,
        schema: str = "public",
        timeout: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = f"{url.rstrip('/')}/rest/v1"
        self._schema = schema
        headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Accept-Profile": schema,
            "Content-Profile": schema,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    # -----------------------------------------------------------------------
    # HTTP helpers (mirrors SupabaseStore pattern)
    # -----------------------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None) -> list[dict]:
        try:
            resp = self._client.get(path, params=params or {})
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase request failed: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise StoreError(f"Supabase GET {path} failed with status {resp.status_code}")
        return resp.json()

    def _post(self, path: str, body: Any, prefer: str = "return=representation") -> httpx.Response:
        try:
            resp = self._client.post(path, json=body, headers={"Prefer": prefer})
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase request failed: {exc.__class__.__name__}") from exc
        return resp

    def _patch(self, path: str, params: dict, body: Any) -> list[dict]:
        try:
            resp = self._client.patch(
                path, params=params, json=body, headers={"Prefer": "return=representation"}
            )
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase request failed: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise StoreError(f"Supabase PATCH {path} failed with status {resp.status_code}")
        return resp.json()

    # -----------------------------------------------------------------------
    # Departments
    # -----------------------------------------------------------------------
    def list_departments(self) -> list[dict]:
        return self._get("/departments", {"select": "*", "order": "name.asc"})

    def get_department(self, dept_id: str) -> Optional[dict]:
        rows = self._get("/departments", {"select": "*", "id": f"eq.{dept_id}"})
        return rows[0] if rows else None

    # -----------------------------------------------------------------------
    # SLA Policies & Stage Targets
    # -----------------------------------------------------------------------
    def list_sla_policies(self) -> list[dict]:
        return self._get("/sla_policies", {"select": "*", "order": "created_at.asc"})

    def get_sla_policy(self, policy_id: str) -> Optional[dict]:
        rows = self._get("/sla_policies", {"select": "*", "id": f"eq.{policy_id}"})
        return rows[0] if rows else None

    def create_sla_policy(self, policy: dict) -> dict:
        if not policy.get("id"):
            policy = {**policy, "id": str(uuid.uuid4())}
        resp = self._post("/sla_policies", policy)
        if resp.status_code >= 400:
            raise StoreError(f"Failed to create SLA policy: {resp.status_code}")
        data = resp.json()
        return data[0] if isinstance(data, list) else data

    def list_sla_stage_targets(self, policy_id: Optional[str] = None) -> list[dict]:
        params = {"select": "*", "order": "created_at.asc"}
        if policy_id:
            params["policy_id"] = f"eq.{policy_id}"
        return self._get("/sla_stage_targets", params)

    def create_sla_stage_target(self, data: dict) -> dict:
        if not data.get("id"):
            data = {**data, "id": str(uuid.uuid4())}
        resp = self._post("/sla_stage_targets", data)
        if resp.status_code >= 400:
            raise StoreError(f"Failed to create stage target: {resp.status_code}")
        res = resp.json()
        return res[0] if isinstance(res, list) else res

    def _get_stage_target(self, policy_id: str, stage: str) -> Optional[dict]:
        rows = self._get(
            "/sla_stage_targets",
            {"select": "*", "policy_id": f"eq.{policy_id}", "stage": f"eq.{stage}"},
        )
        return rows[0] if rows else None

    # -----------------------------------------------------------------------
    # Applications
    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # Presentation hydration (read-only; nothing is persisted)
    # -----------------------------------------------------------------------
    def _decorate_applications(self, rows: list[dict]) -> None:
        """Add assigned_officer_name (from department_users), project_name (from projects)
        and legacy_operational (explicit demo metadata) to application rows, in place."""
        if not rows:
            return
        officer_ids = sorted({r["assigned_officer_id"] for r in rows if r.get("assigned_officer_id")})
        names: dict[str, str] = {}
        if officer_ids:
            for u in self._get("/department_users", {"select": "id,name", "id": f"in.({','.join(officer_ids)})"}):
                names[u["id"]] = u.get("name")
        project_ids = sorted({r["project_id"] for r in rows if r.get("project_id")})
        projects: dict[str, str] = {}
        if project_ids:
            quoted = ",".join('"' + p.replace('"', "") + '"' for p in project_ids)
            for p in self._get("/projects", {"select": "id,name", "id": f"in.({quoted})"}):
                projects[p["id"]] = p.get("name")
        for r in rows:
            r["assigned_officer_name"] = names.get(r.get("assigned_officer_id"))
            r["project_name"] = projects.get(r.get("project_id"))
            r["legacy_operational"] = legacy_operational_info(r.get("project_id"), r.get("application_id"))

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
        params: dict[str, str] = {
            "select": "*,sla_instances(*),sla_policies(*)",
            "order": "created_at.desc",
        }
        if department_id:
            params["department_id"] = f"eq.{department_id}"
        if project_id:
            params["project_id"] = f"eq.{project_id}"
        if status:
            params["current_stage"] = f"eq.{status}"
        if requirement_id:
            params["requirement_id"] = f"eq.{requirement_id}"
        if officer_id:
            params["assigned_officer_id"] = f"eq.{officer_id}"
        if date_from:
            params["created_at"] = f"gte.{date_from}"
        if date_to:
            params["created_at"] = f"lte.{date_to}"

        # PostgREST query
        rows = self._get("/applications", params)

        # In-memory filter for text search if provided
        if search:
            q = search.lower()
            rows = [
                r for r in rows
                if q in (r.get("title") or "").lower()
                or q in (r.get("applicant_name") or "").lower()
                or q in (r.get("application_id") or "").lower()
                or q in (r.get("project_id") or "").lower()
            ]

        # Enrich with SLA
        enriched = []
        for row in rows:
            r = copy.deepcopy(row)
            sla_inst_list = r.pop("sla_instances", [])
            sla_inst = sla_inst_list[0] if isinstance(sla_inst_list, list) and sla_inst_list else sla_inst_list
            policy_list = r.pop("sla_policies", [])
            policy = policy_list[0] if isinstance(policy_list, list) and policy_list else policy_list

            sla_info = _compute_sla_state(
                policy if isinstance(policy, dict) else None,
                r.get("created_at"),
                r.get("completed_at"),
            )
            r["sla"] = sla_info
            enriched.append(r)
        self._decorate_applications(enriched)

        if sla_state:
            enriched = [r for r in enriched if r["sla"]["state"] == sla_state]

        total = len(enriched)
        page = enriched[offset: offset + limit]
        return {"total": total, "items": page}

    def get_application(self, app_id: str, department_id: Optional[str] = None) -> Optional[dict]:
        params: dict[str, str] = {
            "select": "*,sla_instances(*),sla_policies(*)",
            "id": f"eq.{app_id}",
        }
        if department_id:
            params["department_id"] = f"eq.{department_id}"

        rows = self._get("/applications", params)
        if not rows:
            return None

        app = copy.deepcopy(rows[0])
        sla_inst_list = app.pop("sla_instances", [])
        sla_inst = sla_inst_list[0] if isinstance(sla_inst_list, list) and sla_inst_list else sla_inst_list
        policy_list = app.pop("sla_policies", [])
        policy = policy_list[0] if isinstance(policy_list, list) and policy_list else policy_list

        app["sla"] = _compute_sla_state(
            policy if isinstance(policy, dict) else None,
            app.get("created_at"),
            app.get("completed_at"),
        )
        app["sla_instance"] = sla_inst
        self._decorate_applications([app])

        # Stage history
        app["stage_history"] = self._get(
            "/application_stage_history",
            {"select": "*", "application_id": f"eq.{app_id}", "order": "created_at.asc"},
        )
        # Assignment history
        app["assignment_history"] = self._get(
            "/assignment_history",
            {"select": "*", "application_id": f"eq.{app_id}", "order": "created_at.asc"},
        )
        # Operational events
        app["operational_events"] = self._get(
            "/operational_events",
            {"select": "*", "application_id": f"eq.{app_id}", "order": "created_at.asc"},
        )

        return app

    def create_application(self, data: dict) -> dict:
        app_id = str(uuid.uuid4())
        # Sequential application code
        existing = self._get("/applications", {"select": "id"})
        n = len(existing) + 1
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
            "created_at": _now(),
            "updated_at": _now(),
            "completed_at": None,
        }

        # 1. Insert application
        resp = self._post("/applications", record)
        if resp.status_code >= 400:
            raise StoreError(f"Failed to insert application: {resp.status_code} {resp.text}")

        # 2. Insert initial stage history
        stage_record = {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "previous_stage": None,
            "new_stage": ApplicationStage.SUBMITTED.value,
            "actor": data.get("actor", "system"),
            "reason": "Application submitted",
            "created_at": _now(),
        }
        self._post("/application_stage_history", stage_record)

        # 3. Insert operational event
        event_record = {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "event_type": "APPLICATION_SUBMITTED",
            "message": f"Application {application_number} submitted",
            "actor": data.get("actor", "system"),
            "created_at": _now(),
        }
        self._post("/operational_events", event_record)

        # 4. Insert SLA instance
        sla_policy_id = data.get("sla_policy_id")
        if not sla_policy_id:
            policies = self.list_sla_policies()
            sla_policy_id = policies[0]["id"] if policies else None

        sla_record = {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "policy_id": sla_policy_id,
            "started_at": _now(),
            "completed_at": None,
            "created_at": _now(),
        }
        self._post("/sla_instances", sla_record)

        return record

    def transition_stage(
        self,
        app_id: str,
        new_stage: str,
        actor: str,
        reason: Optional[str],
        department_id: Optional[str] = None,
    ) -> dict:
        app = self.get_application(app_id, department_id=department_id)
        if not app:
            raise ValueError(f"Application {app_id} not found")

        current = ApplicationStage(app["current_stage"])
        next_stage = ApplicationStage(new_stage)

        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if next_stage not in allowed:
            raise ValueError(
                f"Invalid transition: {current.value} → {next_stage.value}. "
                f"Allowed from {current.value}: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        now_str = _now()
        patch_data: dict[str, Any] = {
            "current_stage": next_stage.value,
            "updated_at": now_str,
        }
        if next_stage in (ApplicationStage.APPROVED, ApplicationStage.REJECTED):
            patch_data["completed_at"] = now_str
            # Mark SLA instance as completed
            self._patch("/sla_instances", {"application_id": f"eq.{app_id}"}, {"completed_at": now_str})

        # Update application
        self._patch("/applications", {"id": f"eq.{app_id}"}, patch_data)

        # Insert transition record
        self._post("/application_stage_history", {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "previous_stage": current.value,
            "new_stage": next_stage.value,
            "actor": actor,
            "reason": reason,
            "created_at": now_str,
        })

        # Insert operational event
        self._post("/operational_events", {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "event_type": "STAGE_TRANSITION",
            "message": f"Stage changed from {current.value} to {next_stage.value}" + (f": {reason}" if reason else ""),
            "actor": actor,
            "created_at": now_str,
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
        app = self.get_application(app_id, department_id=department_id)
        if not app:
            raise ValueError(f"Application {app_id} not found")

        now_str = _now()
        prev_officer = app.get("assigned_officer_id")

        self._patch("/applications", {"id": f"eq.{app_id}"}, {
            "assigned_officer_id": officer_id,
            "updated_at": now_str,
        })

        self._post("/assignment_history", {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "officer_id": officer_id,
            "officer_name": officer_name,
            "assigned_by": actor,
            "reason": reason,
            "created_at": now_str,
        })

        self._post("/operational_events", {
            "id": str(uuid.uuid4()),
            "application_id": app_id,
            "event_type": "OFFICER_ASSIGNED" if not prev_officer else "OFFICER_REASSIGNED",
            "message": f"Assigned to {officer_name}",
            "actor": actor,
            "created_at": now_str,
        })

        return self.get_application(app_id, department_id=department_id)

    # -----------------------------------------------------------------------
    # Dashboard & SLA Intelligence
    # -----------------------------------------------------------------------
    def get_dashboard_stats(self, department_id: Optional[str] = None) -> dict:
        all_apps = self.list_applications(department_id=department_id, limit=500)["items"]
        # CURRENT workload excludes explicitly-named legacy operational records (still listed and
        # retained in full; only these summary metrics leave them out).
        apps = [a for a in all_apps if not a.get("legacy_operational")]
        legacy_excluded = len(all_apps) - len(apps)
        now = datetime.now(timezone.utc)

        total = len(apps)
        pending = sum(1 for a in apps if a["current_stage"] == ApplicationStage.SUBMITTED.value)
        in_progress = sum(1 for a in apps if a["current_stage"] not in (
            ApplicationStage.SUBMITTED.value, ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value
        ))
        completed = sum(1 for a in apps if a["current_stage"] in (
            ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value
        ))

        at_risk = sum(1 for a in apps if not a.get("completed_at") and a.get("sla", {}).get("state") == SlaState.AT_RISK.value)
        breached = sum(1 for a in apps if not a.get("completed_at") and a.get("sla", {}).get("state") == SlaState.BREACHED.value)

        pipeline = {}
        for stage in ApplicationStage:
            pipeline[stage.value] = sum(1 for a in apps if a["current_stage"] == stage.value)

        recent = []
        for a in all_apps[:10]:
            recent.append({
                "id": a["id"],
                "application_id": a.get("application_id"),
                "project_id": a.get("project_id"),
                "project_name": a.get("project_name"),
                "assigned_officer_name": a.get("assigned_officer_name"),
                "legacy_operational": a.get("legacy_operational"),
                "requirement_id": a.get("requirement_id"),
                "title": a.get("title"),
                "current_stage": a.get("current_stage"),
                "assigned_officer_id": a.get("assigned_officer_id"),
                "sla_state": a.get("sla", {}).get("state"),
                "created_at": a.get("created_at"),
            })

        attention = []
        for a in apps:
            reasons = []
            if not a.get("assigned_officer_id"):
                reasons.append("Unassigned")
            if a["current_stage"] == ApplicationStage.INFORMATION_REQUESTED.value:
                reasons.append("Awaiting information")
            sla_st = a.get("sla", {}).get("state")
            if sla_st in (SlaState.AT_RISK.value, SlaState.BREACHED.value):
                reasons.append(_SLA_REASON[getattr(sla_st, "value", sla_st)])
            if reasons:
                attention.append({
                    "id": a["id"],
                    "application_id": a.get("application_id"),
                    "project_name": a.get("project_name"),
                    "title": a.get("title"),
                    "current_stage": a.get("current_stage"),
                    "reasons": reasons,
                    "sla_state": sla_st,
                })

        return {
            "kpis": {
                "total": total,
                "pending": pending,
                "in_progress": in_progress,
                "completed": completed,
                "sla_at_risk": at_risk,
                "sla_breached": breached,
                "legacy_records_excluded": legacy_excluded,
            },
            "pipeline": [{"stage": k, "count": v} for k, v in pipeline.items()],
            "recent_applications": recent,
            "attention_required": attention,
        }

    def get_timeline(self, app_id: str, department_id: Optional[str] = None) -> list[dict]:
        app = self.get_application(app_id, department_id=department_id)
        if not app:
            raise ValueError(f"Application {app_id} not found")
        return self._get("/operational_events", {"application_id": f"eq.{app_id}", "order": "created_at.asc"})

    def get_sla_dashboard(self, department_id: Optional[str] = None) -> dict:
        apps = self.list_applications(department_id=department_id, limit=500)["items"]
        now = datetime.now(timezone.utc)

        enriched = []
        for a in apps:
            sla_info = a.get("sla", {})
            age_hours = _hours_between(a.get("created_at"), now.isoformat()) or 0.0
            enriched.append({
                "id": a["id"],
                "application_id": a.get("application_id"),
                "title": a.get("title"),
                "current_stage": a.get("current_stage"),
                "department_id": a.get("department_id"),
                "requirement_id": a.get("requirement_id"),
                "assigned_officer_id": a.get("assigned_officer_id"),
                "assigned_officer_name": a.get("assigned_officer_name"),
                "project_id": a.get("project_id"),
                "project_name": a.get("project_name"),
                "legacy_operational": a.get("legacy_operational"),
                "sla_state": sla_info.get("state"),
                "due_at": sla_info.get("due_at"),
                "warning_at": sla_info.get("warning_at"),
                "elapsed_pct": sla_info.get("elapsed_pct", 0.0),
                "age_hours": round(age_hours, 2),
                "created_at": a.get("created_at"),
                "completed_at": a.get("completed_at"),
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
        enriched.sort(key=lambda x: (sla_order.get(x["sla_state"], 9), -x["age_hours"]))

        stage_performance = self.get_sla_stage_performance(department_id=department_id)

        breach_by_stage: dict[str, int] = {}
        for a in enriched:
            if a["sla_state"] in (SlaState.BREACHED.value, SlaState.AT_RISK.value):
                st = a["current_stage"]
                breach_by_stage[st] = breach_by_stage.get(st, 0) + 1

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
        # Fetch applications in department
        params = {"select": "id"}
        if department_id:
            params["department_id"] = f"eq.{department_id}"
        apps = self._get("/applications", params)
        app_ids = [a["id"] for a in apps]

        if not app_ids:
            return []

        # Query stage histories for these applications
        # PostgREST in syntax: application_id=in.(id1,id2,...)
        in_clause = f"in.({','.join(app_ids[:100])})"
        history_rows = self._get(
            "/application_stage_history",
            {"select": "*", "application_id": in_clause, "order": "created_at.asc"}
        )

        histories_by_app: dict[str, list[dict]] = {}
        for h in history_rows:
            histories_by_app.setdefault(h["application_id"], []).append(h)

        all_durations: dict[str, list[float]] = {}
        stage_entry_counts: dict[str, int] = {}
        stage_completed_counts: dict[str, int] = {}

        for app_id, hlist in histories_by_app.items():
            durations = _compute_stage_durations(hlist)
            for st, h_list in durations.items():
                all_durations.setdefault(st, []).extend(h_list)

            sorted_h = sorted(hlist, key=lambda x: x.get("created_at", ""))
            for i, entry in enumerate(sorted_h):
                st = entry.get("new_stage")
                if st:
                    stage_entry_counts[st] = stage_entry_counts.get(st, 0) + 1
                    if i < len(sorted_h) - 1:
                        stage_completed_counts[st] = stage_completed_counts.get(st, 0) + 1

        targets = self.list_sla_stage_targets()
        targets_by_stage = {t["stage"]: t for t in targets}

        results = []
        for stage_enum in ApplicationStage:
            st = stage_enum.value
            hours_list = all_durations.get(st, [])
            avg_h = statistics.mean(hours_list) if hours_list else None
            med_h = _median(hours_list)
            min_h = min(hours_list) if hours_list else None
            max_h = max(hours_list) if hours_list else None

            target = targets_by_stage.get(st)
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
        dash = self.get_sla_dashboard(department_id=department_id)
        apps = dash["applications"]
        if sla_state:
            apps = [a for a in apps if a["sla_state"] == sla_state]
        return {"total": len(apps), "items": apps[offset: offset + limit]}

    # -----------------------------------------------------------------------
    # Bottleneck Analytics (Government-only)
    # -----------------------------------------------------------------------
    def get_bottleneck_report(self, department_id: Optional[str] = None) -> dict:
        now = datetime.now(timezone.utc)
        apps = self.list_applications(department_id=department_id, limit=500)["items"]
        total_apps = len(apps)

        terminal = {ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value}
        active_apps = [a for a in apps if a["current_stage"] not in terminal]
        total_active = len(active_apps)

        backlog: dict[str, list[dict]] = {}
        for app in active_apps:
            st = app["current_stage"]
            backlog.setdefault(st, []).append(app)

        # Stage durations
        app_ids = [a["id"] for a in apps]
        all_stage_durations: dict[str, list[float]] = {}
        app_stage_entry: dict[str, dict[str, str]] = {}
        throughput_7d: dict[str, int] = {}
        throughput_30d: dict[str, int] = {}

        if app_ids:
            in_clause = f"in.({','.join(app_ids[:100])})"
            history_rows = self._get(
                "/application_stage_history",
                {"select": "*", "application_id": in_clause, "order": "created_at.asc"}
            )
            histories_by_app: dict[str, list[dict]] = {}
            for h in history_rows:
                histories_by_app.setdefault(h["application_id"], []).append(h)

            seven_days_ago = (now - timedelta(days=7)).isoformat()
            thirty_days_ago = (now - timedelta(days=30)).isoformat()

            for aid, hlist in histories_by_app.items():
                durations = _compute_stage_durations(hlist)
                for st, h_list in durations.items():
                    all_stage_durations.setdefault(st, []).extend(h_list)

                sorted_h = sorted(hlist, key=lambda x: x.get("created_at", ""))
                if sorted_h:
                    last = sorted_h[-1]
                    app_stage_entry[aid] = {last.get("new_stage", ""): last.get("created_at", "")}

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
            st = stage_enum.value
            if st in terminal:
                continue

            stage_apps = backlog.get(st, [])
            st_backlog = len(stage_apps)

            sla_states = [a.get("sla", {}).get("state") for a in stage_apps]
            at_risk_count = sum(1 for s in sla_states if s == SlaState.AT_RISK.value)
            breached_count = sum(1 for s in sla_states if s == SlaState.BREACHED.value)
            breach_pct = breached_count / st_backlog if st_backlog > 0 else 0.0

            dur_list = all_stage_durations.get(st, [])
            avg_h = statistics.mean(dur_list) if dur_list else None
            med_h = _median(dur_list)
            min_h = min(dur_list) if dur_list else None
            max_h = max(dur_list) if dur_list else None

            aging_7d = 0
            aging_14d = 0
            aging_30d = 0
            for a in stage_apps:
                aid = a["id"]
                entered_at = app_stage_entry.get(aid, {}).get(st)
                if entered_at:
                    h = _hours_between(entered_at, now.isoformat()) or 0.0
                    if h >= 720:
                        aging_30d += 1
                    if h >= 336:
                        aging_14d += 1
                    if h >= 168:
                        aging_7d += 1

            score = _bottleneck_score(avg_h, st_backlog, breach_pct)
            stage_metrics.append({
                "stage": st,
                "backlog": st_backlog,
                "avg_duration_hours": round(avg_h, 2) if avg_h is not None else None,
                "median_duration_hours": round(med_h, 2) if med_h is not None else None,
                "min_duration_hours": round(min_h, 2) if min_h is not None else None,
                "max_duration_hours": round(max_h, 2) if max_h is not None else None,
                "entry_count": len(dur_list) + st_backlog,
                "completed_count": len(dur_list),
                "at_risk_count": at_risk_count,
                "breached_count": breached_count,
                "sla_breach_pct": round(breach_pct, 4),
                "bottleneck_score": round(score, 4),
                "rank": 0,
                "aging_7d": aging_7d,
                "aging_14d": aging_14d,
                "aging_30d": aging_30d,
                "throughput_7d": throughput_7d.get(st, 0),
                "throughput_30d": throughput_30d.get(st, 0),
            })

        stage_metrics.sort(key=lambda m: -m["bottleneck_score"])
        for i, m in enumerate(stage_metrics):
            m["rank"] = i + 1

        officers = self.get_bottleneck_officers(department_id=department_id)

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
            "officers": officers,
            "top_bottleneck_stage": top_stage,
            "top_bottleneck_score": top_score,
        }

    def get_bottleneck_stages(self, department_id: Optional[str] = None) -> list[dict]:
        return self.get_bottleneck_report(department_id=department_id)["stages"]

    def get_bottleneck_officers(self, department_id: Optional[str] = None) -> list[dict]:
        apps = self.list_applications(department_id=department_id, limit=500)["items"]
        users = self.list_department_users(department_id=department_id)
        user_names = {u["id"]: u["name"] for u in users}

        terminal = {ApplicationStage.APPROVED.value, ApplicationStage.REJECTED.value}
        officer_counts: dict[str, dict] = {}

        for a in apps:
            oid = a.get("assigned_officer_id")
            if not oid:
                continue
            if oid not in officer_counts:
                officer_counts[oid] = {
                    "officer_id": oid,
                    "officer_name": user_names.get(oid, oid),
                    "active": 0,
                    "completed": 0,
                    "at_risk": 0,
                    "breached": 0,
                }
            st = a["current_stage"]
            if st in terminal:
                officer_counts[oid]["completed"] += 1
            else:
                officer_counts[oid]["active"] += 1
                sla_state = a.get("sla", {}).get("state")
                if sla_state == SlaState.AT_RISK.value:
                    officer_counts[oid]["at_risk"] += 1
                elif sla_state == SlaState.BREACHED.value:
                    officer_counts[oid]["breached"] += 1

        result = []
        for oid, d in officer_counts.items():
            result.append({
                "officer_id": oid,
                "officer_name": d["officer_name"],
                "department_id": department_id,
                "role": "DEPARTMENT_OFFICER",
                "is_active": True,
                "active_applications": d["active"],
                "completed_applications": d["completed"],
                "total_applications": d["active"] + d["completed"],
                "at_risk_count": d["at_risk"],
                "breached_count": d["breached"],
            })
        result.sort(key=lambda x: -x["active_applications"])
        return result

    def get_bottleneck_trends(self, department_id: Optional[str] = None, days: int = 14) -> list[dict]:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=days)).isoformat()

        params = {"select": "id"}
        if department_id:
            params["department_id"] = f"eq.{department_id}"
        apps = self._get("/applications", params)
        app_ids = [a["id"] for a in apps]

        if not app_ids:
            return []

        in_clause = f"in.({','.join(app_ids[:100])})"
        history_rows = self._get(
            "/application_stage_history",
            {"select": "*", "application_id": in_clause, "created_at": f"gte.{cutoff}", "order": "created_at.asc"}
        )

        trends: dict[str, dict[str, dict[str, int]]] = {}
        for row in history_rows:
            ts = row.get("created_at", "")
            date = ts[:10]
            st = row.get("new_stage")
            prev = row.get("previous_stage")
            if st:
                trends.setdefault(date, {}).setdefault(st, {"entered": 0, "exited": 0})
                trends[date][st]["entered"] += 1
            if prev:
                trends.setdefault(date, {}).setdefault(prev, {"entered": 0, "exited": 0})
                trends[date][prev]["exited"] += 1

        result = []
        for date in sorted(trends.keys()):
            for st, counts in trends[date].items():
                result.append({
                    "date": date,
                    "stage": st,
                    "entered": counts["entered"],
                    "exited": counts["exited"],
                })
        return result

    # -----------------------------------------------------------------------
    # User Management
    # -----------------------------------------------------------------------
    def list_department_users(self, department_id: Optional[str] = None) -> list[dict]:
        params = {"select": "*,departments(name)", "order": "created_at.asc"}
        if department_id:
            params["department_id"] = f"eq.{department_id}"
        rows = self._get("/department_users", params)
        for r in rows:
            dept = r.pop("departments", None)
            r["department_name"] = dept.get("name") if isinstance(dept, dict) else None
        return rows

    def get_department_user(self, user_id: str) -> Optional[dict]:
        rows = self._get("/department_users", {"select": "*,departments(name)", "id": f"eq.{user_id}"})
        if not rows:
            return None
        r = rows[0]
        dept = r.pop("departments", None)
        r["department_name"] = dept.get("name") if isinstance(dept, dict) else None
        return r

    def create_department_user(self, data: dict) -> dict:
        if not data.get("id"):
            data = {**data, "id": str(uuid.uuid4())}
        data["created_at"] = _now()
        data["updated_at"] = _now()
        resp = self._post("/department_users", data)
        if resp.status_code >= 400:
            raise StoreError(f"Failed to create department user: {resp.status_code} {resp.text}")
        res = resp.json()
        return res[0] if isinstance(res, list) else res

    def update_department_user(self, user_id: str, data: dict) -> dict:
        data["updated_at"] = _now()
        rows = self._patch("/department_users", {"id": f"eq.{user_id}"}, data)
        if not rows:
            raise ValueError(f"Department user {user_id} not found")
        updated = rows[0]
        auth_uid = updated.get("supabase_auth_uid")
        if auth_uid:
            prof_data = {}
            if "role" in data:
                prof_data["iris_role"] = data["role"]
            if "department_id" in data:
                prof_data["department_id"] = data["department_id"]
            if prof_data:
                self._patch("/user_profiles", {"supabase_auth_uid": f"eq.{auth_uid}"}, prof_data)
        return updated

    def get_user_profile_by_auth_uid(self, supabase_auth_uid: str) -> Optional[dict]:
        rows = self._get("/user_profiles", {"select": "*,departments(name)", "supabase_auth_uid": f"eq.{supabase_auth_uid}"})
        if not rows:
            # Check department_users
            du_rows = self._get("/department_users", {"select": "*,departments(name)", "supabase_auth_uid": f"eq.{supabase_auth_uid}"})
            if du_rows:
                du = du_rows[0]
                dept = du.pop("departments", None)
                return {
                    "id": du["id"],
                    "supabase_auth_uid": supabase_auth_uid,
                    "email": du.get("email"),
                    "full_name": du.get("name"),
                    "iris_role": du.get("role", "DEPARTMENT_OFFICER"),
                    "department_id": du.get("department_id"),
                    "department_name": dept.get("name") if isinstance(dept, dict) else None,
                    "is_active": du.get("is_active", True),
                    "pending_government_link": False,
                }
            return None

        p = rows[0]
        dept = p.pop("departments", None)
        p["department_name"] = dept.get("name") if isinstance(dept, dict) else None
        return p

    def create_or_update_user_profile(self, data: dict) -> dict:
        auth_uid = data.get("supabase_auth_uid")
        if not auth_uid:
            raise ValueError("supabase_auth_uid is required")

        existing = self._get("/user_profiles", {"select": "*", "supabase_auth_uid": f"eq.{auth_uid}"})
        if existing:
            profile_id = existing[0]["id"]
            patch_data = {k: v for k, v in data.items() if k in ("email", "full_name", "avatar_url", "provider")}
            patch_data["updated_at"] = _now()
            rows = self._patch("/user_profiles", {"id": f"eq.{profile_id}"}, patch_data)
            return rows[0] if rows else existing[0]

        record = {
            "id": str(uuid.uuid4()),
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
        resp = self._post("/user_profiles", record)
        if resp.status_code >= 400:
            raise StoreError(f"Failed to create user profile: {resp.status_code} {resp.text}")
        res = resp.json()
        return res[0] if isinstance(res, list) else res

    def list_user_profiles(self, pending_only: bool = False) -> list[dict]:
        params = {"select": "*,departments(name)", "order": "created_at.desc"}
        if pending_only:
            params["pending_government_link"] = "eq.true"
        rows = self._get("/user_profiles", params)
        for r in rows:
            dept = r.pop("departments", None)
            r["department_name"] = dept.get("name") if isinstance(dept, dict) else None
        return rows

    def link_user_to_department(
        self,
        profile_id: str,
        department_id: str,
        role: str,
        name: Optional[str] = None,
    ) -> dict:
        profiles = self._get("/user_profiles", {"select": "*", "id": f"eq.{profile_id}"})
        if not profiles:
            raise ValueError(f"User profile {profile_id} not found")
        profile = profiles[0]

        valid_roles = {"DEPARTMENT_OFFICER", "DEPARTMENT_MANAGER", "DEPARTMENT_ADMIN"}
        if role not in valid_roles:
            raise ValueError(f"Invalid government role: {role}. Must be one of {valid_roles}")

        depts = self._get("/departments", {"select": "id,name", "id": f"eq.{department_id}"})
        if not depts:
            raise ValueError(f"Department {department_id} not found")

        auth_uid = profile.get("supabase_auth_uid")
        display_name = name or profile.get("full_name") or profile.get("email") or auth_uid

        # Update profile
        self._patch(
            "/user_profiles",
            {"id": f"eq.{profile_id}"},
            {"iris_role": role, "department_id": department_id, "pending_government_link": False, "updated_at": _now()}
        )

        # Upsert department_users
        existing_du = self._get("/department_users", {"select": "*", "supabase_auth_uid": f"eq.{auth_uid}"}) if auth_uid else []
        if existing_du:
            self._patch(
                "/department_users",
                {"id": f"eq.{existing_du[0]['id']}"},
                {"role": role, "department_id": department_id, "name": display_name, "is_active": True, "updated_at": _now()}
            )
        else:
            self._post("/department_users", {
                "id": str(uuid.uuid4()),
                "department_id": department_id,
                "user_id": auth_uid,
                "supabase_auth_uid": auth_uid,
                "name": display_name,
                "email": profile.get("email"),
                "role": role,
                "is_active": True,
                "created_at": _now(),
                "updated_at": _now(),
            })

        updated = self.get_user_profile_by_auth_uid(auth_uid)
        return updated or profile
