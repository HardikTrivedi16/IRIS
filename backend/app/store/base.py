"""
Persistence interface implemented by both ``MemoryStore`` (local/dev/CI
fallback) and ``SupabaseStore`` (production). The API layer only depends on
this interface, never on a concrete backend, so swapping persistence never
touches routing or engine code.

Design notes
------------
* Regulatory data (conditions/rules/rule-versions/requirements/registers) is
  NOT part of this interface. It is loaded straight from the versioned
  ``regulatory-data/`` directory by ``engine_service.py`` and treated as
  read-only, authoritative source data — see docs/architecture.md
  "Regulatory data architecture". Supabase only ever holds *runtime/
  application* state: projects, project facts, documents, decisions,
  decision snapshots, and audit records.
* Decisions, decision snapshots, and audit records are append-only:
  ``save_decision`` must refuse to silently overwrite a decision_id with
  different content (mirrors ``iris_engine.snapshot.DecisionStore``'s own
  immutability contract, just backed by a durable store instead of a
  process-local dict).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class StoreError(Exception):
    """Raised when the persistence backend itself fails (connection error,
    non-2xx response, etc). Callers should catch this and respond with a
    generic, non-leaking error — never propagate the raw exception message
    from an underlying HTTP/DB client to an API client."""


class DecisionConflictError(Exception):
    """Raised when attempting to store a Decision/Snapshot under a
    decision_id that already exists with *different* content. A Decision
    Snapshot must never be silently overwritten (Phase 9 Section 11/12)."""


class Store(ABC):
    # --- Projects ------------------------------------------------------
    @abstractmethod
    def list_projects(self, owner_id: Optional[str] = None, include_unowned: bool = False) -> list[dict]: ...

    @abstractmethod
    def get_project(self, project_id: str) -> Optional[dict]: ...

    @abstractmethod
    def create_project(self, project: dict) -> dict: ...

    # --- Project facts ---------------------------------------------------
    @abstractmethod
    def get_project_facts(self, project_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def merge_project_facts(self, project_id: str, facts: dict[str, Any]) -> dict[str, Any]: ...

    # --- Documents -------------------------------------------------------
    @abstractmethod
    def list_documents(self, project_id: str) -> list[dict]: ...

    @abstractmethod
    def create_document(self, document: dict) -> dict: ...

    # --- Project requirements & activity (industry UI tracking data) ------
    # Concrete (non-abstract) so demo/in-memory backends inherit a safe empty
    # default; SupabaseStore overrides these to read the real tables added in
    # migration 0006. This is application/tracking data, never engine
    # regulatory data (which is file-based and read by engine_service).
    def list_project_requirements(self, project_id: str) -> list[dict]:
        return []

    def list_activity_events(self, project_id: str) -> list[dict]:
        return []

    def list_document_metadata(self, project_id: str) -> list[dict]:
        """Descriptive document metadata (migration 0005 ``document_metadata``)
        for this project's company — used for dated renewals. Empty by default
        (demo/in-memory has no metadata table)."""
        return []

    # --- Decisions / snapshots / audit (append-only) ----------------------
    @abstractmethod
    def save_decision(self, decision: dict, project_facts: dict[str, Any]) -> dict:
        """Persists a Decision (+ its Snapshot + Audit record). ``project_facts``
        is the full fact dict the engine was actually given for this
        evaluation (used only to build the Snapshot's input_fact_snapshot,
        via iris_engine.snapshot.build_snapshot — never stored inside
        decision_payload itself, which stays a verbatim copy of the
        engine's own Decision dict). Must raise DecisionConflictError if
        decision_id already exists with different semantic content, and
        must be a no-op (return the existing record) if it already exists
        with identical content."""

    @abstractmethod
    def get_decision(self, decision_id: str) -> Optional[dict]: ...

    @abstractmethod
    def list_decisions(self, project_id: str, requirement_id: Optional[str] = None) -> list[dict]: ...
