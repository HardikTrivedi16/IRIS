"""
Grievance persistence — in-memory (demo/tests) and Supabase (migration 0007).

Authorization is NOT done here: routers check project ownership (industry)
or department isolation (government) before calling the store, exactly like
the rest of the API. ``grievance_history`` is append-only in both backends.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from .base import StoreError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number() -> str:
    return "GRV-" + uuid.uuid4().hex[:8].upper()


class MemoryGrievanceStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._history: dict[str, list[dict]] = {}

    def create(self, record: dict, actor: dict) -> dict:
        gid = str(uuid.uuid4())
        row = {**record, "id": gid, "grievance_number": _number(), "status": "OPEN",
               "assigned_officer_id": None, "assigned_officer_name": None,
               "resolution_note": None, "created_at": _now(), "updated_at": _now()}
        self._rows[gid] = row
        self._history[gid] = []
        self._append(gid, None, "OPEN", actor, "Grievance submitted by applicant.")
        return self.get(gid)

    def _append(self, gid: str, frm: Optional[str], to: str, actor: dict, note: Optional[str]) -> None:
        self._history[gid].append({
            "id": str(uuid.uuid4()), "grievance_id": gid, "from_status": frm, "to_status": to,
            "actor_id": actor["id"], "actor_name": actor.get("name"), "actor_role": actor["role"],
            "note": note, "created_at": _now(),
        })

    def get(self, gid: str) -> Optional[dict]:
        row = self._rows.get(gid)
        if not row:
            return None
        out = copy.deepcopy(row)
        out["history"] = copy.deepcopy(self._history.get(gid, []))
        return out

    def list(self, *, project_id: Optional[str] = None, department_id: Optional[str] = None,
             status: Optional[str] = None) -> list[dict]:
        rows = [r for r in self._rows.values()
                if (project_id is None or r["project_id"] == project_id)
                and (department_id is None or r["department_id"] == department_id)
                and (status is None or r["status"] == status)]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [copy.deepcopy(r) for r in rows]

    def update(self, gid: str, changes: dict, *, frm: str, to: str, actor: dict, note: Optional[str]) -> dict:
        row = self._rows[gid]
        row.update(changes)
        row["updated_at"] = _now()
        self._append(gid, frm, to, actor, note)
        return self.get(gid)


class SupabaseGrievanceStore:
    def __init__(self, url: str, service_role_key: str, schema: str = "public") -> None:
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Accept-Profile": schema,
                "Content-Profile": schema,
            },
            timeout=15.0,
        )

    def _req(self, method: str, path: str, **kw) -> Any:
        try:
            resp = self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase request failed: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            # Most likely cause: migration 0007 not applied yet.
            raise StoreError(f"Supabase {method} {path} failed with status {resp.status_code}")
        return resp.json() if resp.content else None

    def _history_append(self, gid: str, frm: Optional[str], to: str, actor: dict, note: Optional[str]) -> None:
        self._req("POST", "/grievance_history", json={
            "grievance_id": gid, "from_status": frm, "to_status": to, "actor_id": actor["id"],
            "actor_name": actor.get("name"), "actor_role": actor["role"], "note": note,
        }, headers={"Prefer": "return=minimal"})

    def create(self, record: dict, actor: dict) -> dict:
        rows = self._req("POST", "/grievances",
                         json={**record, "grievance_number": _number(), "status": "OPEN"},
                         headers={"Prefer": "return=representation"})
        gid = rows[0]["id"]
        self._history_append(gid, None, "OPEN", actor, "Grievance submitted by applicant.")
        return self.get(gid)

    def get(self, gid: str) -> Optional[dict]:
        rows = self._req("GET", "/grievances", params={"select": "*", "id": f"eq.{gid}"})
        if not rows:
            return None
        row = rows[0]
        row["history"] = self._req("GET", "/grievance_history", params={
            "select": "*", "grievance_id": f"eq.{gid}", "order": "created_at.asc"})
        return row

    def list(self, *, project_id: Optional[str] = None, department_id: Optional[str] = None,
             status: Optional[str] = None) -> list[dict]:
        params = {"select": "*", "order": "created_at.desc"}
        if project_id:
            params["project_id"] = f"eq.{project_id}"
        if department_id:
            params["department_id"] = f"eq.{department_id}"
        if status:
            params["status"] = f"eq.{status}"
        return self._req("GET", "/grievances", params=params)

    def update(self, gid: str, changes: dict, *, frm: str, to: str, actor: dict, note: Optional[str]) -> dict:
        self._req("PATCH", "/grievances", params={"id": f"eq.{gid}"},
                  json={**changes, "updated_at": _now()}, headers={"Prefer": "return=minimal"})
        self._history_append(gid, frm, to, actor, note)
        return self.get(gid)


_memory_store: Optional[MemoryGrievanceStore] = None


def get_grievance_store():
    """Supabase when configured; in-memory in demo mode; fail closed otherwise
    (mirrors get_department_store)."""
    from ..config import get_settings

    global _memory_store
    settings = get_settings()
    if settings.supabase_configured:
        return SupabaseGrievanceStore(settings.supabase_url, settings.supabase_service_role_key,
                                      settings.supabase_schema)
    if settings.iris_demo_mode:
        if _memory_store is None:
            _memory_store = MemoryGrievanceStore()
        return _memory_store
    raise StoreError("Grievance store unavailable: Supabase not configured and demo mode is off.")
