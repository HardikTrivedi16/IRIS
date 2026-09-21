"""
Grievance preparation / tracking / hand-off — see ``app/grievances.py``.

Industry (project owner; authorization via ``get_project``):
    GET  /api/v1/projects/{project_id}/applications
    GET  /api/v1/projects/{project_id}/grievances
    POST /api/v1/projects/{project_id}/grievances
    GET  /api/v1/projects/{project_id}/grievances/{grievance_id}

Government (``require_government`` + department isolation, like every
/api/v1/department route):
    GET  /api/v1/department/grievances
    GET  /api/v1/department/grievances/{grievance_id}
    POST /api/v1/department/grievances/{grievance_id}/assign      (manager/admin)
    POST /api/v1/department/grievances/{grievance_id}/transition

Nothing is filed automatically; creation is an explicit applicant action.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..grievances import (
    ASSIGNED,
    CATEGORIES,
    DISCLAIMER,
    OPEN,
    GrievanceRuleError,
    applicant_view,
    build_context_snapshot,
    check_transition,
)
from ..schemas import GrievanceAssignIn, GrievanceCreateIn, GrievanceTransitionIn
from ..security import CurrentUser, Role, get_optional_user, require_government, require_role
from ..store.base import StoreError
from ..store.department_store import get_department_store
from ..store.grievance_store import get_grievance_store
from .projects import get_project

logger = logging.getLogger("iris.api.grievances")
router = APIRouter(prefix="/api/v1", tags=["grievances"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except StoreError as exc:
        logger.error("Grievance/department store error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Grievance storage is unavailable (has migration 0007 been applied?)",
        ) from exc


def _actor(user: Optional[CurrentUser]) -> dict:
    if user is None:
        return {"id": "anonymous-demo", "name": "Demo applicant", "role": "INDUSTRY_USER"}
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {"id": user.user_id, "name": user.name, "role": role}


def _with_meta(row: dict) -> dict:
    row = dict(row)
    row["category_label"] = CATEGORIES.get(row.get("category"), row.get("category"))
    row["disclaimer"] = DISCLAIMER
    return row


# --- Industry ---------------------------------------------------------------------

@router.get("/projects/{project_id}/applications")
def list_project_applications(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> list[dict]:
    """The project's own applications with stage + SLA timing only (no officer
    identities or internal notes)."""
    get_project(project_id, user=user)
    result = _call(get_department_store().list_applications, project_id=project_id, limit=200)
    return [applicant_view(a) for a in result["items"]]


@router.get("/projects/{project_id}/grievances")
def list_project_grievances(
    project_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> list[dict]:
    get_project(project_id, user=user)
    return [_with_meta(g) for g in _call(get_grievance_store().list, project_id=project_id)]


@router.post("/projects/{project_id}/grievances", status_code=201)
def create_grievance(
    project_id: str,
    body: GrievanceCreateIn,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    if user is not None and user.is_government() and not user.is_demo:
        raise HTTPException(status_code=403, detail="Only the applicant can raise a grievance.")
    if not body.acknowledge_not_statutory:
        raise HTTPException(status_code=422, detail=DISCLAIMER)

    app = _call(get_department_store().get_application, body.application_id)
    if not app or app.get("project_id") != project_id:
        # Same 404 whether it doesn't exist or belongs to another project.
        raise HTTPException(status_code=404, detail="Application not found for this project")

    actor = _actor(user)
    record = {
        "project_id": project_id,
        "application_id": app["id"],
        "department_id": app["department_id"],
        "category": body.category,
        "description": body.description,
        "context_snapshot": build_context_snapshot(app),
        "raised_by": actor["id"],
        "raised_by_name": actor["name"],
    }
    return _with_meta(_call(get_grievance_store().create, record, actor))


@router.get("/projects/{project_id}/grievances/{grievance_id}")
def get_project_grievance(
    project_id: str,
    grievance_id: str,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    get_project(project_id, user=user)
    g = _call(get_grievance_store().get, grievance_id)
    if not g or g["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Grievance not found")
    return _with_meta(g)


# --- Government -------------------------------------------------------------------

def _dept_grievance(grievance_id: str, user: CurrentUser) -> dict:
    g = _call(get_grievance_store().get, grievance_id)
    if not g or (user.department_id and g["department_id"] != user.department_id):
        raise HTTPException(status_code=404, detail="Grievance not found")
    return g


@router.get("/department/grievances")
def list_department_grievances(
    status: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(require_government),
) -> list[dict]:
    return [_with_meta(g) for g in _call(
        get_grievance_store().list, department_id=user.department_id, status=status)]


@router.get("/department/grievances/{grievance_id}")
def get_department_grievance(
    grievance_id: str,
    user: CurrentUser = Depends(require_government),
) -> dict:
    return _with_meta(_dept_grievance(grievance_id, user))


@router.post("/department/grievances/{grievance_id}/assign")
def assign_grievance(
    grievance_id: str,
    body: GrievanceAssignIn,
    user: CurrentUser = Depends(require_role(Role.DEPARTMENT_MANAGER, Role.DEPARTMENT_ADMIN)),
) -> dict:
    g = _dept_grievance(grievance_id, user)
    if g["status"] not in (OPEN, ASSIGNED):
        raise HTTPException(status_code=422, detail=f"Cannot assign a grievance that is {g['status']}.")
    officers = _call(get_department_store().list_department_users, department_id=g["department_id"])
    officer = next(
        (o for o in officers if o.get("id") == body.officer_id and o.get("is_active", True)), None
    )
    if officer is None:
        raise HTTPException(status_code=422, detail="Officer is not an active member of this department.")
    return _with_meta(_call(
        get_grievance_store().update, grievance_id,
        {"status": ASSIGNED, "assigned_officer_id": officer["id"],
         "assigned_officer_name": officer.get("name")},
        frm=g["status"], to=ASSIGNED, actor=_actor(user),
        note=body.note or f"Assigned to {officer.get('name')}.",
    ))


@router.post("/department/grievances/{grievance_id}/transition")
def transition_grievance(
    grievance_id: str,
    body: GrievanceTransitionIn,
    user: CurrentUser = Depends(require_government),
) -> dict:
    g = _dept_grievance(grievance_id, user)
    try:
        check_transition(g["status"], body.to_status, body.note)
    except GrievanceRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    changes: dict = {"status": body.to_status}
    if body.to_status == "RESOLVED":
        changes["resolution_note"] = body.note
    return _with_meta(_call(
        get_grievance_store().update, grievance_id, changes,
        frm=g["status"], to=body.to_status, actor=_actor(user), note=body.note,
    ))
