"""
In-memory persistence backend.

Used automatically when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not
configured (see app/store/__init__.py::get_store). Backed by plain
process-local dicts plus the engine's own ``DecisionStore`` for the
append-only immutability contract on decisions — reusing that class (rather
than reimplementing the same "never silently overwrite" rule twice) keeps
the in-memory and Supabase backends demonstrably consistent in behavior.

Nothing here is regulatory data. It seeds two demo *application* projects
that mirror the two prototype projects already in the existing IRIS
frontend mock data (MahaPharm Formulations, FreshBite Foods) purely so the
API has something to return out of the box in local/dev/CI use — no
regulatory content is invented by this seed.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from iris_engine.snapshot import DecisionStore, SnapshotConflictError, build_snapshot
from iris_engine.audit import build_audit_record
from iris_engine.reproducibility import semantically_equal

from .base import Store, DecisionConflictError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SEED_PROJECTS: list[dict] = [
    {
        "id": "mahapharm",
        "name": "MahaPharm Formulations Pvt. Ltd.",
        "industry": "pharmaceutical",
        "activity": "Pharmaceutical formulation manufacturing",
        "location": "Maharashtra",
        "stage": "pre-establishment",
        "scale": "medium",
        "workers": 250,
        "characteristics": {
            "hazardousChemicals": True,
            "hazardousWaste": True,
            "wastewater": True,
            "airEmissions": True,
            "waterUse": True,
            "chemicalStorage": True,
        },
        "created_at": _now(),
        "updated_at": _now(),
    },
    {
        "id": "freshbite",
        "name": "FreshBite Foods Pvt. Ltd.",
        "industry": "food",
        "activity": "Food processing / manufacturing",
        "location": "Maharashtra",
        "stage": "pre-establishment",
        "scale": "medium",
        "workers": 120,
        "characteristics": {
            "hazardousChemicals": False,
            "hazardousWaste": False,
            "wastewater": True,
            "airEmissions": False,
            "waterUse": True,
            "chemicalStorage": False,
        },
        "created_at": _now(),
        "updated_at": _now(),
    },
]


class MemoryStore(Store):
    def __init__(self) -> None:
        self._projects: dict[str, dict] = {p["id"]: copy.deepcopy(p) for p in _SEED_PROJECTS}
        self._facts: dict[str, dict[str, Any]] = {"mahapharm": {}, "freshbite": {}}
        self._documents: dict[str, list[dict]] = {"mahapharm": [], "freshbite": []}
        self._decisions = DecisionStore()
        self._decision_meta: dict[str, dict] = {}  # decision_id -> {project_id, requirement_id, full_decision, audit}

    # --- Projects ------------------------------------------------------
    def list_projects(self, owner_id: Optional[str] = None, include_unowned: bool = False) -> list[dict]:
        projects = list(self._projects.values())
        if owner_id:
            projects = [
                p for p in projects
                if p.get("owner_id") == owner_id or (include_unowned and p.get("owner_id") is None)
            ]
        elif not include_unowned:
            projects = [p for p in projects if p.get("owner_id") is not None]
        return [copy.deepcopy(p) for p in projects]

    def get_project(self, project_id: str) -> Optional[dict]:
        p = self._projects.get(project_id)
        return copy.deepcopy(p) if p else None

    def create_project(self, project: dict) -> dict:
        pid = project.get("id") or str(uuid.uuid4())
        record = {
            **project,
            "id": pid,
            "owner_id": project.get("owner_id"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._projects[pid] = record
        self._facts.setdefault(pid, {})
        self._documents.setdefault(pid, [])
        return copy.deepcopy(record)

    # --- Project facts ---------------------------------------------------
    def get_project_facts(self, project_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._facts.get(project_id, {}))

    def merge_project_facts(self, project_id: str, facts: dict[str, Any]) -> dict[str, Any]:
        current = self._facts.setdefault(project_id, {})
        current.update(facts)
        if project_id in self._projects:
            self._projects[project_id]["updated_at"] = _now()
        return copy.deepcopy(current)

    # --- Documents -------------------------------------------------------
    def list_documents(self, project_id: str) -> list[dict]:
        return [copy.deepcopy(d) for d in self._documents.get(project_id, [])]

    def create_document(self, document: dict) -> dict:
        pid = document["project_id"]
        record = {
            **document,
            "id": document.get("id") or str(uuid.uuid4()),
            "uploaded_at": document.get("uploaded_at") or _now(),
        }
        self._documents.setdefault(pid, []).append(record)
        return copy.deepcopy(record)

    # --- Decisions / snapshots / audit -------------------------------------
    def save_decision(self, decision: dict, project_facts: dict) -> dict:
        decision_id = decision["decision_id"]

        # decision_id is a hash of everything that determines *semantic*
        # content and deliberately excludes evaluated_at (see
        # iris_engine.snapshot.compute_decision_id's docstring) -- so two
        # separate evaluate calls for identical inputs legitimately produce
        # the same decision_id but two different (evaluated_at-bearing)
        # Snapshots. DecisionStore.put() enforces byte-exact equality
        # including evaluated_at, so it must only ever be called the FIRST
        # time a given decision_id is stored; every subsequent save for the
        # same decision_id is resolved here via semantic equality instead,
        # exactly like SupabaseStore already does for its `decisions` table.
        existing = self._decision_meta.get(decision_id)
        if existing is not None:
            if not semantically_equal(existing["decision"], decision):
                raise DecisionConflictError(
                    f"decision_id {decision_id!r} already stored with different content"
                )
            return copy.deepcopy(existing)

        snapshot = build_snapshot(decision=decision, project_facts=project_facts)
        try:
            stored_snapshot = self._decisions.put(snapshot)
        except SnapshotConflictError as exc:
            # Should not happen given the guard above, but never silently
            # swallow an actual immutability violation if it somehow does.
            raise DecisionConflictError(str(exc)) from exc

        audit = build_audit_record(decision)
        meta = {
            "decision_id": decision_id,
            "project_id": decision.get("project_id"),
            "requirement_id": decision.get("requirement_id"),
            "decision": decision,
            "snapshot": stored_snapshot,
            "audit": audit,
            "stored_at": _now(),
        }
        self._decision_meta[decision_id] = meta
        return copy.deepcopy(meta)

    def get_decision(self, decision_id: str) -> Optional[dict]:
        meta = self._decision_meta.get(decision_id)
        return copy.deepcopy(meta) if meta else None

    def list_decisions(self, project_id: str, requirement_id: Optional[str] = None) -> list[dict]:
        out = [
            copy.deepcopy(m)
            for m in self._decision_meta.values()
            if m["project_id"] == project_id
            and (requirement_id is None or m["requirement_id"] == requirement_id)
        ]
        out.sort(key=lambda m: m["stored_at"], reverse=True)
        return out
