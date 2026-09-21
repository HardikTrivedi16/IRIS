"""
SLA Intelligence router — Government-only.

All endpoints require authentication with a DEPARTMENT_* role.
Industry users (INDUSTRY_USER) receive HTTP 403.
SLA data is NEVER exposed to Industry users via this router.

Endpoints:
  GET /api/v1/department/sla/dashboard          — comprehensive SLA health
  GET /api/v1/department/sla/applications       — applications with SLA status
  GET /api/v1/department/sla/stage-performance  — stage-level performance vs targets

SLA Calculation (single authoritative path)
-------------------------------------------
Application-level SLA state (WITHIN_SLA / AT_RISK / BREACHED / COMPLETED) is
computed by _compute_sla_state() in department_store.py using:
  - sla_instances.started_at
  - sla_policies.duration_hours + warning_pct
This is the PRIMARY SLA metric returned by all endpoints.

Stage-level performance uses sla_stage_targets to show avg/median duration
vs configured targets per stage. This is ADDITIONAL analytics context —
it does not replace the application-level SLA state.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..store.department_store import get_department_store
from ..store.base import StoreError
from ..security import require_government, CurrentUser
from ..department_schemas import CreateSLAPolicyIn, CreateSLAStageTargetIn

logger = logging.getLogger("iris.api.sla")

router = APIRouter(
    prefix="/api/v1/department/sla",
    tags=["department-sla"],
)


def _store_err(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except StoreError as exc:
        logger.error("Department store error: %s", exc)
        raise HTTPException(status_code=502, detail="Persistence backend unavailable") from exc


# ---------------------------------------------------------------------------
# SLA Policies (moved here from department.py — old paths kept in department.py
# for backward compatibility with existing tests)
# ---------------------------------------------------------------------------

@router.get("/policies")
def list_sla_policies(user: CurrentUser = Depends(require_government)) -> list[dict]:
    """List all configurable SLA policies. Government-only."""
    return get_department_store().list_sla_policies()


@router.post("/policies", status_code=201)
def create_sla_policy(
    body: CreateSLAPolicyIn,
    user: CurrentUser = Depends(require_government),
) -> dict:
    """Create a new SLA policy. Government-only."""
    return get_department_store().create_sla_policy(body.model_dump())


# ---------------------------------------------------------------------------
# SLA Stage Targets
# ---------------------------------------------------------------------------

@router.get("/stage-targets")
def list_sla_stage_targets(
    policy_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_government),
) -> list[dict]:
    """List per-stage SLA targets (used for stage-performance analytics)."""
    return get_department_store().list_sla_stage_targets(policy_id=policy_id)


@router.post("/stage-targets", status_code=201)
def create_sla_stage_target(
    body: CreateSLAStageTargetIn,
    user: CurrentUser = Depends(require_government),
) -> dict:
    """Create a stage-level SLA target for a policy."""
    ds = get_department_store()
    policy = ds.get_sla_policy(body.policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"SLA policy {body.policy_id!r} not found")
    return ds.create_sla_stage_target(body.model_dump())


# ---------------------------------------------------------------------------
# SLA Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_sla_dashboard(user: CurrentUser = Depends(require_government)) -> dict:
    """
    Comprehensive SLA intelligence dashboard. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_sla_dashboard,
        department_id=user.department_id,
    )


@router.get("/applications")
def get_sla_applications(
    sla_state: Optional[str] = Query(None, description="Filter: WITHIN_SLA, AT_RISK, BREACHED, COMPLETED"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_government),
) -> dict:
    """
    Applications with full SLA status. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_sla_applications,
        department_id=user.department_id,
        sla_state=sla_state,
        limit=limit,
        offset=offset,
    )


@router.get("/stage-performance")
def get_sla_stage_performance(user: CurrentUser = Depends(require_government)) -> list[dict]:
    """
    Per-stage SLA performance analytics. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_sla_stage_performance,
        department_id=user.department_id,
    )
