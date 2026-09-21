"""
Bottleneck Analytics router — Government-only.

All endpoints require authentication with a DEPARTMENT_* role.
Industry users receive HTTP 403. Bottleneck data is NEVER exposed to
Industry users via this router.

Endpoints:
  GET /api/v1/department/bottlenecks/report    — full bottleneck report
  GET /api/v1/department/bottlenecks/stages    — per-stage metrics
  GET /api/v1/department/bottlenecks/officers  — officer workload
  GET /api/v1/department/bottlenecks/trends    — processing trends (last N days)

Methodology (deterministic, documented)
----------------------------------------
All metrics computed from real application records, stage_history timestamps,
and sla_instances. No fabricated scores or invented data.

Bottleneck score formula:
  score = (avg_duration_hours × 0.40) + (backlog × 0.35) + (sla_breach_pct × 100 × 0.25)

Where:
  avg_duration_hours — mean time applications spent in this stage (completed sojourns)
  backlog            — count of active (non-terminal) applications in this stage
  sla_breach_pct     — fraction of backlog with BREACHED overall SLA

Stage rank 1 = worst bottleneck.

Median computation: Python sort + midpoint (no external library, accurate for
typical dataset sizes; optimize with SQL PERCENTILE_CONT for 100K+ records).

Architecture: data is structured to support NetworkX graph analysis in a
future phase without schema changes.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..store.department_store import get_department_store
from ..store.base import StoreError
from ..security import require_government, CurrentUser

logger = logging.getLogger("iris.api.bottlenecks")

router = APIRouter(
    prefix="/api/v1/department/bottlenecks",
    tags=["department-bottlenecks"],
)


def _store_err(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except StoreError as exc:
        logger.error("Department store error: %s", exc)
        raise HTTPException(status_code=502, detail="Persistence backend unavailable") from exc


@router.get("/report")
def get_bottleneck_report(user: CurrentUser = Depends(require_government)) -> dict:
    """
    Full deterministic bottleneck report. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_bottleneck_report,
        department_id=user.department_id,
    )


@router.get("/stages")
def get_bottleneck_stages(user: CurrentUser = Depends(require_government)) -> list[dict]:
    """
    Per-stage bottleneck metrics. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_bottleneck_stages,
        department_id=user.department_id,
    )


@router.get("/officers")
def get_officer_workload(user: CurrentUser = Depends(require_government)) -> list[dict]:
    """
    Officer workload analytics. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_bottleneck_officers,
        department_id=user.department_id,
    )


@router.get("/trends")
def get_processing_trends(
    days: int = Query(default=14, ge=1, le=90, description="Number of days to look back"),
    user: CurrentUser = Depends(require_government),
) -> list[dict]:
    """
    Processing trends. Strictly scoped to user's department.
    """
    return _store_err(
        get_department_store().get_bottleneck_trends,
        days=days,
        department_id=user.department_id,
    )
