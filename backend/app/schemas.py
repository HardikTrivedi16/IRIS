from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class ProjectCharacteristics(BaseModel):
    hazardousChemicals: bool = False
    hazardousWaste: bool = False
    wastewater: bool = False
    airEmissions: bool = False
    waterUse: bool = False
    chemicalStorage: bool = False

    model_config = {"extra": "allow"}


class ProjectIn(BaseModel):
    """Project intake. Fields mirror the existing ``public.projects`` columns
    (migration 0001) — nothing here is a regulatory fact. Regulatory inputs
    are captured separately as Project Facts (POST /projects/{id}/facts),
    driven by the dataset-derived fact registry."""

    # Strip surrounding whitespace so "   " is rejected by min_length rather
    # than stored as a blank-looking project.
    model_config = {"str_strip_whitespace": True}

    id: Optional[str] = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Omit to auto-generate a uuid. Must not already exist.",
    )
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=100)
    activity: Optional[str] = Field(default=None, max_length=500)
    location: Optional[str] = Field(default=None, max_length=300)
    stage: Optional[str] = Field(default=None, max_length=50)
    scale: Optional[str] = Field(default=None, max_length=50)
    # Mirrors the DB check constraint (workers is null or workers >= 0) so the
    # in-memory store rejects the same values Postgres would.
    workers: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    characteristics: ProjectCharacteristics = Field(default_factory=ProjectCharacteristics)


class ProjectFactsIn(BaseModel):
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Engine-shaped project facts, e.g. {'project.industry': 'FOOD'}",
    )


class DocumentIn(BaseModel):
    name: str
    storage_path: Optional[str] = None
    status: Literal["uploaded", "extracted", "missing-info", "mismatch"] = "uploaded"
    linked_requirement_ids: list[str] = Field(default_factory=list)


EvaluationMode = Literal["PRODUCTION", "NON_PRODUCTION"]


class EvaluateRequest(BaseModel):
    project_id: str
    requirement_id: str
    evaluation_mode: EvaluationMode = "PRODUCTION"
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Ad-hoc facts merged on top of any facts already stored for this project "
        "(request body wins on key collision). Optional if the project already has the "
        "facts this requirement's Rule Version needs.",
    )
    persist: Optional[bool] = Field(
        default=None,
        description="Persist the resulting Decision (+ snapshot + audit) via the store. "
        "Defaults to True for PRODUCTION, False for NON_PRODUCTION (lazy diagnostics).",
    )


class EvaluateAllRequest(BaseModel):
    project_id: str
    evaluation_mode: EvaluationMode = "PRODUCTION"
    facts: dict[str, Any] = Field(default_factory=dict)
    persist: Optional[bool] = Field(
        default=None,
        description="Defaults to True for PRODUCTION, False for NON_PRODUCTION.",
    )


class ChangeImpactRequest(BaseModel):
    """A proposed change to this project's Project Facts, evaluated as a
    preview. ``proposed_facts`` is merged onto a COPY of the project's
    stored facts — it is never persisted (see app/change_impact.py).

    Keys are validated against the dataset-derived fact registry
    (app/fact_registry.py), so an unsupported key or a wrong-typed value is
    rejected with a per-key 422 rather than silently evaluating to UNKNOWN.
    """

    proposed_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Engine-shaped fact overrides, e.g. "
        "{'project.dairy_liquid_milk_capacity': 60000}. A null value clears "
        "a fact back to unknown.",
    )
    evaluation_mode: EvaluationMode = "PRODUCTION"


class DecisionProofRequest(BaseModel):
    """Decision Proof for a hypothetical fact set. ``hypothetical_facts`` are
    validated against the fact registry, merged onto a COPY of the stored
    facts and never persisted; the proof is labelled HYPOTHETICAL."""

    evaluation_mode: EvaluationMode = "PRODUCTION"
    hypothetical_facts: dict[str, Any] = Field(default_factory=dict)


class ObservationSource(BaseModel):
    kind: Literal["DOCUMENT", "MANUAL"] = "DOCUMENT"
    document_id: Optional[str] = Field(default=None, max_length=200)
    document_name: Optional[str] = Field(default=None, max_length=300)
    page: Optional[int] = Field(default=None, ge=1, le=100_000)
    evidence_text: Optional[str] = Field(default=None, max_length=2000)


class ConsistencyObservation(BaseModel):
    """One value as it appears in one source. ``confidence`` is the upstream
    extractor's per-field confidence, if any (human-entered values: omit).
    Callers cannot claim PROJECT_RECORD provenance — the server adds the
    project's own confirmed record itself."""

    field: str = Field(max_length=64)
    value: Union[str, float, int, None] = None
    unit: Optional[str] = Field(default=None, max_length=40)
    confidence: Optional[float] = None
    is_reference: bool = False
    observation_id: Optional[str] = Field(default=None, max_length=100)
    source: ObservationSource = Field(default_factory=ObservationSource)


class ConsistencyCheckRequest(BaseModel):
    observations: list[ConsistencyObservation] = Field(default_factory=list, max_length=200)
    required_fields: list[str] = Field(default_factory=list, max_length=20)
    include_project_record: bool = True
    as_of_date: Optional[str] = Field(
        default=None,
        description="ISO date for expiry checks. Defaults to today (server, UTC).",
    )


class GrievanceCreateIn(BaseModel):
    """Explicit applicant submission. ``acknowledge_not_statutory`` must be
    true: IRIS grievance tracking is preparation/hand-off, not a statutory
    filing — the applicant confirms they understand that."""

    model_config = {"str_strip_whitespace": True}

    application_id: str = Field(min_length=1, max_length=64)
    category: Literal["PROCESSING_DELAY", "INFORMATION_REQUEST_UNCLEAR", "DOCUMENT_HANDLING", "OTHER"]
    description: str = Field(min_length=10, max_length=4000)
    acknowledge_not_statutory: bool


class GrievanceAssignIn(BaseModel):
    officer_id: str = Field(min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)


class GrievanceTransitionIn(BaseModel):
    to_status: Literal["UNDER_REVIEW", "RESOLVED", "CLOSED"]
    note: Optional[str] = Field(default=None, max_length=4000)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
