"""
Pydantic schemas for the Department/Government portal API.

Stages are derived from the existing project/engine architecture:
  SUBMITTED → UNDER_REVIEW → INFORMATION_REQUESTED → UNDER_REVIEW →
  INSPECTION_SCHEDULED → INSPECTION_COMPLETED → RECOMMENDED →
  APPROVED / REJECTED

This ordering maps naturally onto the existing project stage pipeline
(pre-establishment → construction → commissioning → operations) without
inventing new regulatory/legal semantics.

SLA Note (Single authoritative calculation path)
-------------------------------------------------
Application-level SLA state (WITHIN_SLA / AT_RISK / BREACHED / COMPLETED) is
computed by ``_compute_sla_state()`` in department_store.py using sla_policies
+ sla_instances. This is the primary SLA metric.

Stage-level SLA targets (from sla_stage_targets) are used ONLY for the SLA
dashboard's stage-performance analytics — they do not replace or duplicate the
application-level SLA state. Both are computed in the backend; neither is
hardcoded or fabricated.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Application stage enum
# ---------------------------------------------------------------------------

class ApplicationStage(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    INFORMATION_REQUESTED = "INFORMATION_REQUESTED"
    INSPECTION_SCHEDULED = "INSPECTION_SCHEDULED"
    INSPECTION_COMPLETED = "INSPECTION_COMPLETED"
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Allowed transitions: map current stage → set of reachable next stages
# Server-side validation only — the frontend does NOT enforce this.
ALLOWED_TRANSITIONS: dict[ApplicationStage, set[ApplicationStage]] = {
    ApplicationStage.SUBMITTED: {ApplicationStage.UNDER_REVIEW},
    ApplicationStage.UNDER_REVIEW: {
        ApplicationStage.INFORMATION_REQUESTED,
        ApplicationStage.INSPECTION_SCHEDULED,
        ApplicationStage.RECOMMENDED,
        ApplicationStage.REJECTED,
    },
    ApplicationStage.INFORMATION_REQUESTED: {ApplicationStage.UNDER_REVIEW},
    ApplicationStage.INSPECTION_SCHEDULED: {
        ApplicationStage.INSPECTION_COMPLETED,
        ApplicationStage.UNDER_REVIEW,  # re-open if inspection postponed
    },
    ApplicationStage.INSPECTION_COMPLETED: {
        ApplicationStage.RECOMMENDED,
        ApplicationStage.UNDER_REVIEW,
        ApplicationStage.REJECTED,
    },
    ApplicationStage.RECOMMENDED: {
        ApplicationStage.APPROVED,
        ApplicationStage.REJECTED,
    },
    # Terminal states — no outgoing transitions allowed
    ApplicationStage.APPROVED: set(),
    ApplicationStage.REJECTED: set(),
}


# ---------------------------------------------------------------------------
# SLA state enum
# ---------------------------------------------------------------------------

class SlaState(str, Enum):
    WITHIN_SLA = "WITHIN_SLA"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Request / response models — Applications
# ---------------------------------------------------------------------------

class CreateApplicationIn(BaseModel):
    project_id: str = Field(..., description="Existing project id this application is for")
    requirement_id: str = Field(..., description="Engine requirement id (REQ-####)")
    department_id: str
    title: Optional[str] = None
    applicant_name: Optional[str] = None
    sla_policy_id: Optional[str] = None


class AssignOfficerIn(BaseModel):
    officer_id: str
    officer_name: str
    reason: Optional[str] = None


class TransitionStageIn(BaseModel):
    new_stage: ApplicationStage
    reason: Optional[str] = None
    actor: Optional[str] = Field(default="system", description="User/system performing the transition")


# ---------------------------------------------------------------------------
# Request / response models — SLA Policies & Stage Targets
# ---------------------------------------------------------------------------

class CreateSLAPolicyIn(BaseModel):
    name: str
    requirement_type: Optional[str] = None  # e.g. "environmental", "food" — None = default
    duration_hours: int = Field(..., ge=1, description="Total SLA window in hours")
    warning_pct: float = Field(default=0.75, ge=0.0, le=1.0, description="Fraction of duration at which AT_RISK begins")
    description: Optional[str] = None


class CreateSLAStageTargetIn(BaseModel):
    """Per-stage SLA target within a policy. Used for stage-level performance analytics."""
    policy_id: str = Field(..., description="ID of the SLA policy this target belongs to")
    stage: ApplicationStage
    target_hours: int = Field(..., ge=1, description="Target processing time for this stage in hours")
    warning_pct: float = Field(default=0.75, ge=0.0, le=1.0)
    description: Optional[str] = None


class ApplicationListFilters(BaseModel):
    search: Optional[str] = None
    status: Optional[ApplicationStage] = None
    requirement_id: Optional[str] = None
    officer_id: Optional[str] = None
    sla_state: Optional[SlaState] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Request / response models — Bottleneck Analytics
# ---------------------------------------------------------------------------

class StageBottleneckMetrics(BaseModel):
    """Deterministic bottleneck metrics for a single workflow stage."""
    stage: str
    backlog: int = Field(..., description="Active (non-terminal) applications in this stage")
    avg_duration_hours: Optional[float] = Field(None, description="Average time spent in this stage (completed sojourns)")
    median_duration_hours: Optional[float] = Field(None, description="Median time spent in this stage")
    min_duration_hours: Optional[float] = None
    max_duration_hours: Optional[float] = None
    entry_count: int = Field(..., description="Total applications that have ever entered this stage")
    completed_count: int = Field(..., description="Applications that have exited this stage")
    at_risk_count: int = Field(..., description="Backlog applications whose overall SLA is AT_RISK")
    breached_count: int = Field(..., description="Backlog applications whose overall SLA is BREACHED")
    sla_breach_pct: float = Field(..., description="Fraction of backlog that is BREACHED (0.0–1.0)")
    # Bottleneck score: deterministic formula, documented
    bottleneck_score: float = Field(
        ...,
        description=(
            "Deterministic bottleneck score = "
            "(avg_duration_hours * 0.4) + (backlog * 0.35) + (breach_pct * 100 * 0.25). "
            "Operational heuristic only — not a legal or regulatory metric. "
            "Weights are configurable."
        )
    )
    rank: int = Field(..., description="Stage rank by bottleneck_score (1 = worst)")
    aging_7d: int = Field(..., description="Backlog applications stuck in this stage > 7 days")
    aging_14d: int = Field(..., description="Backlog applications stuck in this stage > 14 days")
    aging_30d: int = Field(..., description="Backlog applications stuck in this stage > 30 days")
    throughput_7d: int = Field(..., description="Applications that exited this stage in the last 7 days")
    throughput_30d: int = Field(..., description="Applications that exited this stage in the last 30 days")


class OfficerWorkloadMetrics(BaseModel):
    officer_id: str
    officer_name: str
    department_id: Optional[str]
    role: str
    is_active: bool
    active_applications: int
    completed_applications: int
    total_applications: int
    at_risk_count: int
    breached_count: int


class ProcessingTrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    stage: str
    entered: int  # applications entering this stage on this date
    exited: int   # applications leaving this stage on this date


class BottleneckReport(BaseModel):
    generated_at: str
    total_active: int  # non-terminal applications
    total_applications: int
    methodology: str = (
        "Deterministic. Scores use real stage_history timestamps + sla_instances. "
        "No fabricated data. Formula: score = (avg_duration_hours * 0.4) + "
        "(backlog * 0.35) + (sla_breach_pct * 100 * 0.25). "
        "Weights documented and configurable. "
        "Median computed in Python (sort + midpoint). "
        "Architecture is ready for NetworkX graph analysis in a future phase."
    )
    stages: list[StageBottleneckMetrics]
    officers: list[OfficerWorkloadMetrics]
    top_bottleneck_stage: Optional[str]
    top_bottleneck_score: Optional[float]


# ---------------------------------------------------------------------------
# Request / response models — User Management (Government Admin)
# ---------------------------------------------------------------------------

class UserProfileOut(BaseModel):
    """IRIS user profile (for admin user management UI)."""
    id: str
    supabase_auth_uid: str
    email: Optional[str]
    full_name: Optional[str]
    iris_role: str
    department_id: Optional[str]
    department_name: Optional[str]
    is_active: bool
    pending_government_link: bool
    provider: Optional[str]
    created_at: str


class LinkUserIn(BaseModel):
    """Admin action: link a user profile to a department + role."""
    user_profile_id: str = Field(..., description="ID of the user_profiles row to link")
    department_id: str
    role: str = Field(..., description="One of DEPARTMENT_OFFICER, DEPARTMENT_MANAGER, DEPARTMENT_ADMIN")
    name: Optional[str] = Field(None, description="Officer display name (defaults to email)")


class UpdateUserIn(BaseModel):
    """Admin action: update a government user's role or active status."""
    role: Optional[str] = None
    is_active: Optional[bool] = None
    department_id: Optional[str] = None


class CreateDepartmentUserIn(BaseModel):
    """Admin action: create a government user record manually (without Supabase Auth link)."""
    name: str
    email: Optional[str] = None
    role: str = Field(default="DEPARTMENT_OFFICER")
    department_id: str


# ---------------------------------------------------------------------------
# SLA Dashboard response types
# ---------------------------------------------------------------------------

class SlaStagePerformance(BaseModel):
    """Per-stage SLA performance analytics."""
    stage: str
    entry_count: int
    completed_count: int
    avg_duration_hours: Optional[float]
    median_duration_hours: Optional[float]
    min_duration_hours: Optional[float]
    max_duration_hours: Optional[float]
    # Stage target (from sla_stage_targets if configured)
    target_hours: Optional[int]
    target_warning_pct: Optional[float]
    vs_target: Optional[str]  # "WITHIN", "AT_RISK", "EXCEEDED", null if no target


class SlaDashboardKpis(BaseModel):
    total: int
    active: int
    completed: int
    within_sla: int
    at_risk: int
    breached: int
    # Aging buckets (non-terminal applications)
    aging_0_7d: int
    aging_7_30d: int
    aging_30_60d: int
    aging_over_60d: int


class SlaApplicationSummary(BaseModel):
    id: str
    application_id: str
    title: Optional[str]
    current_stage: str
    department_id: str
    requirement_id: str
    assigned_officer_name: Optional[str]
    sla_state: str
    due_at: Optional[str]
    warning_at: Optional[str]
    elapsed_pct: float
    age_hours: float
    created_at: str
    completed_at: Optional[str]
