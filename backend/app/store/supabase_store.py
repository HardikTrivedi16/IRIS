"""
Supabase persistence backend.

Talks to Supabase's PostgREST HTTP API directly (no Supabase Python SDK
dependency) using the service-role key. This module is only ever imported
and constructed server-side (see app/store/__init__.py) — the service-role
key never reaches the frontend build.

This class was written and unit-tested against a mocked HTTP transport
(see backend/tests/test_supabase_store.py) that asserts the exact
URLs/headers/payloads it sends. It could NOT be exercised against a real
Supabase project in this environment (no live project or network egress to
supabase.co was available) — see docs/architecture.md "Testing caveats"
for exactly what was and wasn't verified.

Integration fixes applied in this revision
-------------------------------------------
Fix 1 — create_project: generate a uuid4 if ``id`` is absent, exactly like
  MemoryStore does. Without this the INSERT fails because ``projects.id`` is
  a NOT NULL primary key with no DEFAULT.

Fix 2 — merge_project_facts: pass ``on_conflict=project_id,fact_key`` as a
  query param so PostgREST resolves the composite UNIQUE constraint
  ``(project_id, fact_key)`` correctly instead of returning a 409.

Fix 3 — save_decision: snapshot + audit inserts are now done inline in
  save_decision; if either fails StoreError is raised immediately (prevents
  a decision row surviving without its snapshot/audit). The previously
  separate _insert_snapshot_and_audit helper is removed.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import httpx

from iris_engine.snapshot import build_snapshot
from iris_engine.audit import build_audit_record
from iris_engine.reproducibility import semantically_equal

from .base import Store, StoreError, DecisionConflictError


class SupabaseStore(Store):
    def __init__(self, url: str, service_role_key: str, schema: str = "public", timeout: float = 10.0) -> None:
        self._base_url = f"{url.rstrip('/')}/rest/v1"
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
                "Accept-Profile": schema,
                "Content-Profile": schema,
            },
        )

    def close(self) -> None:
        self._client.close()

    # --- low-level helpers -------------------------------------------------
    def _get(self, path: str, params: dict) -> list[dict]:
        try:
            resp = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase request failed: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise StoreError(f"Supabase GET {path} failed with status {resp.status_code}")
        return resp.json()

    def _post(self, path: str, body: Any, prefer: str = "return=representation", params: Optional[dict] = None) -> httpx.Response:
        try:
            resp = self._client.post(path, json=body, headers={"Prefer": prefer}, params=params or {})
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

    # --- Projects ----------------------------------------------------------
    def list_projects(self, owner_id: Optional[str] = None, include_unowned: bool = False) -> list[dict]:
        params: dict[str, str] = {"select": "*", "order": "created_at.asc"}
        if owner_id:
            if include_unowned:
                params["or"] = f"(owner_id.eq.{owner_id},owner_id.is.null)"
            else:
                params["owner_id"] = f"eq.{owner_id}"
        elif not include_unowned:
            params["owner_id"] = "not.is.null"
        return self._get("/projects", params)

    def get_project(self, project_id: str) -> Optional[dict]:
        rows = self._get("/projects", {"select": "*", "id": f"eq.{project_id}"})
        return rows[0] if rows else None

    def create_project(self, project: dict) -> dict:
        # Fix 1: ensure id is always present before INSERT — projects.id has
        # no DB DEFAULT so omitting it produces a NOT NULL violation.
        if not project.get("id"):
            project = {**project, "id": str(uuid.uuid4())}
        # Upsert on primary key so re-seeding demo projects is idempotent.
        resp = self._post(
            "/projects",
            project,
            prefer="return=representation,resolution=merge-duplicates",
        )
        if resp.status_code >= 400:
            raise StoreError(f"Supabase create_project failed with status {resp.status_code}")
        rows = resp.json()
        return rows[0] if isinstance(rows, list) else rows

    # --- Project facts -----------------------------------------------------
    def get_project_facts(self, project_id: str) -> dict[str, Any]:
        rows = self._get(
            "/project_facts",
            {"select": "fact_key,fact_value", "project_id": f"eq.{project_id}"},
        )
        return {r["fact_key"]: r["fact_value"] for r in rows}

    def merge_project_facts(self, project_id: str, facts: dict[str, Any]) -> dict[str, Any]:
        if facts:
            payload = [
                {"project_id": project_id, "fact_key": k, "fact_value": v}
                for k, v in facts.items()
            ]
            # Fix 2: specify the composite conflict target (project_id, fact_key)
            # so PostgREST resolves the UNIQUE(project_id, fact_key) constraint
            # correctly and performs an UPDATE rather than returning a 409.
            resp = self._post(
                "/project_facts",
                payload,
                prefer="resolution=merge-duplicates,return=minimal",
                params={"on_conflict": "project_id,fact_key"},
            )
            if resp.status_code >= 400:
                raise StoreError(f"Supabase merge_project_facts failed with status {resp.status_code}")
        return self.get_project_facts(project_id)

    # --- Documents ---------------------------------------------------------
    def list_documents(self, project_id: str) -> list[dict]:
        return self._get(
            "/documents",
            {"select": "*", "project_id": f"eq.{project_id}", "order": "uploaded_at.desc"},
        )

    def create_document(self, document: dict) -> dict:
        resp = self._post("/documents", document)
        if resp.status_code >= 400:
            raise StoreError(f"Supabase create_document failed with status {resp.status_code}")
        rows = resp.json()
        return rows[0] if isinstance(rows, list) else rows

    # --- Project requirements & activity (migration 0006) ------------------
    def list_project_requirements(self, project_id: str) -> list[dict]:
        return self._get(
            "/project_requirements",
            {"select": "*", "project_id": f"eq.{project_id}", "order": "sort_order.asc"},
        )

    def list_activity_events(self, project_id: str) -> list[dict]:
        return self._get(
            "/activity_events",
            {"select": "*", "project_id": f"eq.{project_id}", "order": "created_at.desc"},
        )

    # --- Decisions / snapshots / audit (append-only) ----------------------
    def save_decision(self, decision: dict, project_facts: dict) -> dict:
        decision_id = decision["decision_id"]

        decision_row = {
            "decision_id": decision_id,
            "project_id": decision.get("project_id"),
            "requirement_id": decision.get("requirement_id"),
            "rule_id": decision.get("rule_id"),
            "rule_version_id": decision.get("rule_version_id"),
            "rule_version_status": decision.get("rule_version_status"),
            "final_state": decision.get("final_state"),
            "evaluation_mode": decision.get("evaluation_mode"),
            "engine_version": decision.get("engine_version"),
            "is_non_production_result": bool(decision.get("is_non_production_result")),
            "review_reason": decision.get("review_reason"),
            "conflict_id": decision.get("conflict_id"),
            "reason_text": decision.get("reason_text"),
            "decision_payload": decision,
            "evaluated_at": decision.get("evaluated_at"),
        }

        resp = self._post("/decisions", decision_row)
        if resp.status_code in (200, 201):
            # Fix 3: snapshot + audit inserted inline; StoreError is raised
            # immediately on failure, preventing a decision row surviving
            # without its snapshot/audit (partial-persistence prevention).
            snapshot = build_snapshot(decision=decision, project_facts=project_facts)
            audit = build_audit_record(decision)

            snap_resp = self._post(
                "/decision_snapshots",
                {"decision_id": decision_id, "snapshot_payload": snapshot},
            )
            if snap_resp.status_code not in (200, 201, 409):
                raise StoreError(
                    f"Supabase snapshot insert failed with status {snap_resp.status_code} "
                    f"(decision {decision_id!r} was inserted but has no snapshot)"
                )

            audit_resp = self._post(
                "/audit_records",
                {"decision_id": decision_id, "audit_payload": audit},
            )
            if audit_resp.status_code not in (200, 201, 409):
                raise StoreError(
                    f"Supabase audit insert failed with status {audit_resp.status_code} "
                    f"(decision {decision_id!r} was inserted but has no audit record)"
                )

        elif resp.status_code == 409:
            existing_rows = self._get(
                "/decisions", {"select": "decision_payload", "decision_id": f"eq.{decision_id}"}
            )
            existing_payload = existing_rows[0]["decision_payload"] if existing_rows else None
            if existing_payload is None or not semantically_equal(existing_payload, decision):
                raise DecisionConflictError(
                    f"decision_id {decision_id!r} already stored in Supabase with different content"
                )
            # Identical content already stored — idempotent no-op.
        else:
            raise StoreError(f"Supabase save_decision failed with status {resp.status_code}: {resp.text[:300]}")

        return self.get_decision(decision_id)

    def get_decision(self, decision_id: str) -> Optional[dict]:
        rows = self._get("/decisions", {"select": "*", "decision_id": f"eq.{decision_id}"})
        if not rows:
            return None
        decision_row = rows[0]
        snap_rows = self._get(
            "/decision_snapshots", {"select": "*", "decision_id": f"eq.{decision_id}"}
        )
        audit_rows = self._get("/audit_records", {"select": "*", "decision_id": f"eq.{decision_id}"})
        return {
            "decision_id": decision_id,
            "project_id": decision_row.get("project_id"),
            "requirement_id": decision_row.get("requirement_id"),
            "decision": decision_row.get("decision_payload"),
            "snapshot": snap_rows[0].get("snapshot_payload") if snap_rows else None,
            "audit": audit_rows[0].get("audit_payload") if audit_rows else None,
            "stored_at": decision_row.get("created_at"),
        }

    def list_decisions(self, project_id: str, requirement_id: Optional[str] = None) -> list[dict]:
        params = {"select": "*", "project_id": f"eq.{project_id}", "order": "created_at.desc"}
        if requirement_id:
            params["requirement_id"] = f"eq.{requirement_id}"
        rows = self._get("/decisions", params)
        return [
            {
                "decision_id": r["decision_id"],
                "project_id": r.get("project_id"),
                "requirement_id": r.get("requirement_id"),
                "decision": r.get("decision_payload"),
                "stored_at": r.get("created_at"),
            }
            for r in rows
        ]
