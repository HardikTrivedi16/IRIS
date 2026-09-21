"""
Department / Government portal API router.

All endpoints are prefixed /api/v1/department and follow the existing
IRIS API style (see projects.py, evaluate.py for patterns).

Security & Department Isolation:
  - All department endpoints require a valid JWT with a DEPARTMENT_* role.
  - In production, missing auth or unauthenticated callers fail closed immediately.
  - Industry users (INDUSTRY_USER) receive HTTP 403 from require_government().
  - Department data is strictly isolated to the caller's assigned department_id.
    A user belonging to department A cannot access or mutate applications,
    SLA metrics, bottleneck data, or officer rosters of department B.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..store.department_store import get_department_store
from ..store import get_store
from ..store.base import StoreError
from ..department_schemas import (
    CreateApplicationIn,
    AssignOfficerIn,
    TransitionStageIn,
    CreateSLAPolicyIn,
    ApplicationStage,
    LinkUserIn,
    UpdateUserIn,
    CreateDepartmentUserIn,
)
from ..security import (
    get_current_user,
    require_government,
    require_role,
    require_department_admin,
    CurrentUser,
    Role,
)

logger = logging.getLogger("iris.api.department")
router = APIRouter(prefix="/api/v1/department", tags=["department"])


def _store_err(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except StoreError as exc:
        logger.error("Department store error: %s", exc)
        raise HTTPException(status_code=502, detail="Persistence backend unavailable") from exc


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_dashboard(user: CurrentUser = Depends(require_government)) -> dict:
    """Real-time department KPIs — strictly scoped to caller's department. Government-only."""
    ds = get_department_store()
    return ds.get_dashboard_stats(department_id=user.department_id)


# ---------------------------------------------------------------------------
# SLA Policies (preserved for backward compatibility — also in /sla router)
# ---------------------------------------------------------------------------

@router.get("/sla/policies")
def list_sla_policies(user: CurrentUser = Depends(require_government)) -> list[dict]:
    return get_department_store().list_sla_policies()


@router.post("/sla/policies", status_code=201)
def create_sla_policy(
    body: CreateSLAPolicyIn,
    user: CurrentUser = Depends(require_department_admin),
) -> dict:
    return get_department_store().create_sla_policy(body.model_dump())


# ---------------------------------------------------------------------------
# Applications (Strict Department Isolation)
# ---------------------------------------------------------------------------

@router.get("/applications")
def list_applications(
    search: Optional[str] = Query(None),
    status: Optional[ApplicationStage] = Query(None),
    requirement_id: Optional[str] = Query(None),
    officer_id: Optional[str] = Query(None),
    sla_state: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_government),
) -> dict:
    ds = get_department_store()
    return ds.list_applications(
        department_id=user.department_id,
        search=search,
        status=status.value if status else None,
        requirement_id=requirement_id,
        officer_id=officer_id,
        sla_state=sla_state,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.post("/applications", status_code=201)
def create_application(
    body: CreateApplicationIn,
    user: CurrentUser = Depends(require_government),
) -> dict:
    # Cross-department check: cannot file into another department
    if user.department_id and body.department_id != user.department_id:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot create application in department '{body.department_id}'. You are assigned to '{user.department_id}'.",
        )

    main_store = get_store()
    try:
        project = main_store.get_project(body.project_id)
    except StoreError:
        project = None
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project {body.project_id!r} not found — create the project first",
        )

    data = body.model_dump()
    data["actor"] = user.name
    data["department_id"] = user.department_id or body.department_id

    ds = get_department_store()
    return ds.create_application(data)


@router.get("/applications/{app_id}")
def get_application(
    app_id: str,
    user: CurrentUser = Depends(require_government),
) -> dict:
    ds = get_department_store()
    app = ds.get_application(app_id, department_id=user.department_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    main_store = get_store()
    try:
        decisions = main_store.list_decisions(
            project_id=app["project_id"],
            requirement_id=app.get("requirement_id"),
        )
        app["engine_decision"] = decisions[0]["decision"] if decisions else None
    except Exception as exc:
        logger.warning("Could not fetch engine decision for application %s: %s", app_id, exc)
        app["engine_decision"] = None

    try:
        project = main_store.get_project(app["project_id"])
        app["project"] = project
    except Exception:
        app["project"] = None

    return app


@router.post("/applications/{app_id}/assign")
def assign_officer(
    app_id: str,
    body: AssignOfficerIn,
    user: CurrentUser = Depends(require_role(Role.DEPARTMENT_MANAGER, Role.DEPARTMENT_ADMIN)),
) -> dict:
    ds = get_department_store()
    app = ds.get_application(app_id, department_id=user.department_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    try:
        return ds.assign_officer(
            app_id=app_id,
            officer_id=body.officer_id,
            officer_name=body.officer_name,
            actor=user.name,
            reason=body.reason,
            department_id=user.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/applications/{app_id}/transition")
def transition_stage(
    app_id: str,
    body: TransitionStageIn,
    user: CurrentUser = Depends(require_government),
) -> dict:
    ds = get_department_store()
    app = ds.get_application(app_id, department_id=user.department_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    try:
        return ds.transition_stage(
            app_id=app_id,
            new_stage=body.new_stage.value,
            actor=body.actor or user.name,
            reason=body.reason,
            department_id=user.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/applications/{app_id}/timeline")
def get_timeline(
    app_id: str,
    user: CurrentUser = Depends(require_government),
) -> list[dict]:
    ds = get_department_store()
    app = ds.get_application(app_id, department_id=user.department_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")
    return ds.get_timeline(app_id, department_id=user.department_id)


# ---------------------------------------------------------------------------
# User Management (Government Admin - Strictly Scoped to Caller's Department)
# ---------------------------------------------------------------------------

@router.get("/users")
def list_department_users(
    department_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_government),
) -> list[dict]:
    """
    List government users. Government-only.
    Strictly scoped to the caller's assigned department_id.
    """
    ds = get_department_store()
    dept_filter = user.department_id or department_id
    return ds.list_department_users(department_id=dept_filter)


@router.post("/users", status_code=201)
def create_department_user(
    body: CreateDepartmentUserIn,
    user: CurrentUser = Depends(require_department_admin),
) -> dict:
    """Create a government user record manually. DEPARTMENT_ADMIN only."""
    ds = get_department_store()
    dept = ds.get_department(body.department_id)
    if not dept:
        raise HTTPException(status_code=404, detail=f"Department {body.department_id!r} not found")

    if user.department_id and body.department_id != user.department_id:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot create officers for department '{body.department_id}'. You are admin of '{user.department_id}'.",
        )

    return ds.create_department_user(body.model_dump())


@router.get("/users/{user_id}")
def get_department_user(
    user_id: str,
    user: CurrentUser = Depends(require_government),
) -> dict:
    """Get government user detail. Strictly scoped to caller's department."""
    ds = get_department_store()
    du = ds.get_department_user(user_id, department_id=user.department_id)
    if not du:
        raise HTTPException(status_code=404, detail=f"Department user {user_id} not found")
    return du


@router.patch("/users/{user_id}")
def update_department_user(
    user_id: str,
    body: UpdateUserIn,
    user: CurrentUser = Depends(require_department_admin),
) -> dict:
    """Update a government user's role or active status. DEPARTMENT_ADMIN only."""
    ds = get_department_store()
    try:
        return ds.update_department_user(
            user_id,
            body.model_dump(exclude_none=True),
            department_id=user.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/users/link-profile")
def link_user_profile(
    body: LinkUserIn,
    user: CurrentUser = Depends(require_department_admin),
) -> dict:
    """
    Admin action: link an IRIS user_profile to caller's department and assign a government role.
    """
    if user.department_id and body.department_id != user.department_id:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot link users to department '{body.department_id}'. You are admin of '{user.department_id}'.",
        )

    ds = get_department_store()
    try:
        return ds.link_user_to_department(
            profile_id=body.user_profile_id,
            department_id=body.department_id,
            role=body.role,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/user-profiles")
def list_user_profiles(
    pending_only: bool = Query(False, description="Only show profiles pending government link"),
    user: CurrentUser = Depends(require_department_admin),
) -> list[dict]:
    """List IRIS user profiles awaiting assignment. DEPARTMENT_ADMIN only."""
    return get_department_store().list_user_profiles(pending_only=pending_only)
