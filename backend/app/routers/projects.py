from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..fact_registry import FactValidationError, fact_registry_index, validate_facts
from ..schemas import ProjectIn, ProjectFactsIn, DocumentIn
from ..security import CurrentUser, get_optional_user
from ..legacy_evidence import annotate_documents
from ..store import get_store
from ..store.base import StoreError

logger = logging.getLogger("iris.api.projects")
router = APIRouter(prefix="/api/v1", tags=["projects"])


def _store_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except StoreError as exc:
        logger.error("Persistence error: %s", exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc


@router.get("/projects")
def list_projects(user: Optional[CurrentUser] = Depends(get_optional_user)) -> list[dict]:
    settings = get_settings()
    # In demo mode, return all projects including unowned demo seed projects
    if settings.iris_demo_mode or (user and user.is_demo):
        return _store_call(
            get_store().list_projects,
            owner_id=user.user_id if user else None,
            include_unowned=True,
        )

    # In production, require authentication
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to list projects.")

    if user.is_industry():
        # Industry users ONLY see their own projects (never unowned or another user's)
        return _store_call(
            get_store().list_projects,
            owner_id=user.user_id,
            include_unowned=False,
        )

    # Government users can list projects
    return _store_call(get_store().list_projects, owner_id=None, include_unowned=True)


@router.post("/projects", status_code=201)
def create_project(
    project: ProjectIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    settings = get_settings()
    if not user and not settings.iris_demo_mode:
        raise HTTPException(status_code=401, detail="Authentication required to create projects.")

    payload = project.model_dump(exclude_none=True)
    if not payload.get("id"):
        payload["id"] = str(uuid.uuid4())
    elif _store_call(get_store().get_project, payload["id"]) is not None:
        # Both stores upsert on the primary key (SupabaseStore uses
        # resolution=merge-duplicates), so without this check a caller could
        # overwrite any existing project — including another user's — and
        # re-stamp its owner_id to themselves. Creation must never modify an
        # existing record. The detail deliberately says nothing about the
        # existing project's owner or contents.
        raise HTTPException(
            status_code=409,
            detail="A project with this id already exists. Omit id to auto-generate one.",
        )
    if user and user.user_id:
        payload["owner_id"] = user.user_id

    return _store_call(get_store().create_project, payload)


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    settings = get_settings()
    project = _store_call(get_store().get_project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Enforce tenant isolation for industry users
    if not settings.iris_demo_mode and (not user or not user.is_demo):
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required.")
        if user.is_industry():
            owner = project.get("owner_id")
            # In production, unowned legacy projects are not accessible to industry users,
            # and projects owned by other users are denied (returns 404 to avoid enumeration)
            if not owner or owner != user.user_id:
                raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    return project


@router.get("/projects/{project_id}/facts")
def get_project_facts(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    return {"project_id": project_id, "facts": _store_call(get_store().get_project_facts, project_id)}


@router.post("/projects/{project_id}/facts")
def set_project_facts(
    project_id: str,
    body: ProjectFactsIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    # Type-check only the keys the regulatory engine actually reads (the
    # dataset-derived registry). A wrong-typed value there would otherwise be
    # stored and later evaluate to UNKNOWN with an opaque engine error; better
    # to refuse it at the door. Other keys — e.g. the `document.*` facts the
    # Documents page stores after human confirmation — pass through
    # unchanged, exactly as before. Values are never coerced.
    registry = fact_registry_index()
    engine_keyed = {k: v for k, v in body.facts.items() if k in registry}
    try:
        validate_facts(engine_keyed)
    except FactValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_project_facts", "errors": exc.errors},
        )
    facts = _store_call(get_store().merge_project_facts, project_id, body.facts)
    return {"project_id": project_id, "facts": facts}


@router.get("/projects/{project_id}/documents")
def list_documents(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> list[dict]:
    get_project(project_id, user=user)
    docs = _store_call(get_store().list_documents, project_id)
    # Presentation-only: mark explicitly-named legacy (prior-facility) evidence.
    return annotate_documents(project_id, docs)


@router.post("/projects/{project_id}/documents", status_code=201)
def create_document(
    project_id: str,
    document: DocumentIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    payload = {"project_id": project_id, **document.model_dump(exclude_none=True)}
    return _store_call(get_store().create_document, payload)


def _to_requirement(row: dict) -> dict:
    """Map a project_requirements DB row to the frontend Requirement shape
    (camelCase, nested documents) so the industry pages consume it unchanged."""
    return {
        "id": row.get("req_key"),
        "name": row.get("name"),
        "authority": row.get("authority") or "—",
        "stage": row.get("stage") or "",
        "status": row.get("status") or "not-ready",
        "applicability": row.get("applicability") or "applicable",
        "documents": {
            "total": row.get("documents_total") or 0,
            "complete": row.get("documents_complete") or 0,
        },
        "dependsOn": row.get("depends_on") or [],
        "blocks": row.get("blocks") or [],
        "source": row.get("source") or "—",
        "description": row.get("description") or "",
        "reason": row.get("reason"),
        "timeline": row.get("timeline") or "—",
    }


@router.get("/projects/{project_id}/requirements")
def list_project_requirements(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> list[dict]:
    """Per-project regulatory readiness checklist (real data, migration 0006).
    Returns [] gracefully if the table has not been created/seeded yet, so the
    UI shows an empty register rather than an error before the SQL is run."""
    get_project(project_id, user=user)
    try:
        rows = get_store().list_project_requirements(project_id)
    except StoreError:
        logger.warning("project_requirements unavailable for %s (run migration 0006?)", project_id)
        return []
    return [_to_requirement(r) for r in rows]


@router.get("/projects/{project_id}/activity")
def list_project_activity(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> list[dict]:
    """Recent application-activity events for the project's Overview timeline.
    Returns [] gracefully if the table/rows are absent."""
    get_project(project_id, user=user)
    try:
        return get_store().list_activity_events(project_id)
    except StoreError:
        logger.warning("activity_events unavailable for %s", project_id)
        return []


@router.get("/projects/{project_id}/decisions")
def list_decisions(
    project_id: str,
    requirement_id: Optional[str] = None,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> list[dict]:
    get_project(project_id, user=user)
    return _store_call(get_store().list_decisions, project_id, requirement_id=requirement_id)

