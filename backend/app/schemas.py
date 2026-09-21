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
    id: Optional[str] = Field(default=None, description="Omit to auto-generate a uuid")
    name: str
    industry: str
    activity: Optional[str] = None
    location: Optional[str] = None
    stage: Optional[str] = None
    scale: Optional[str] = None
    workers: Optional[int] = None
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


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
