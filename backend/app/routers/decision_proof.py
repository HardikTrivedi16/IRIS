"""
Decision Proof — the Rule Engine's own evidence for one requirement.

    GET  /api/v1/projects/{project_id}/decision-proof/{requirement_id}
        ?evaluation_mode=PRODUCTION|NON_PRODUCTION
    POST /api/v1/projects/{project_id}/decision-proof/{requirement_id}
        {"evaluation_mode": ..., "hypothetical_facts": {...}}

Authorization reuses ``get_project`` exactly like every other
``/projects/{id}/*`` sub-resource.

* GET computes the proof from the project's STORED Project Facts only, so it
  always describes the project as it is recorded (``fact_basis: STORED``).
* POST additionally accepts registry-validated hypothetical facts — used for
  the "proposed" side of a Change Impact diff. They are merged onto a copy
  of the stored facts and the proof is labelled ``fact_basis: HYPOTHETICAL``
  with the exact hypothetical values listed.

Nothing is persisted by either.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException

from .. import engine_service
from ..decision_proof import decision_proof_for
from ..fact_registry import FactValidationError, validate_facts
from ..schemas import DecisionProofRequest
from ..security import CurrentUser, get_optional_user
from ..store import get_store
from ..store.base import StoreError
from .projects import get_project

logger = logging.getLogger("iris.api.decision_proof")
router = APIRouter(prefix="/api/v1", tags=["decision-proof"])


def _proof(project_id, requirement_id, evaluation_mode, user, hypothetical=None) -> dict:
    get_project(project_id, user=user)
    if engine_service.get_requirement(requirement_id) is None:
        raise HTTPException(status_code=404, detail=f"Requirement {requirement_id} not found in dataset")
    try:
        validated = validate_facts(hypothetical or {})
    except FactValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_hypothetical_facts", "errors": exc.errors},
        )
    try:
        facts = get_store().get_project_facts(project_id)
    except StoreError as exc:
        logger.error("Persistence error loading facts for %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable") from exc
    try:
        return decision_proof_for(project_id, requirement_id, facts, evaluation_mode, validated)
    except Exception as exc:  # fail safe — never leak internals
        logger.exception("Decision proof failed for %s/%s", project_id, requirement_id)
        raise HTTPException(status_code=500, detail="Decision proof failed") from exc


@router.get("/projects/{project_id}/decision-proof/{requirement_id}")
def get_decision_proof(
    project_id: str,
    requirement_id: str,
    evaluation_mode: Literal["PRODUCTION", "NON_PRODUCTION"] = "PRODUCTION",
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    """Proof from the project's STORED Project Facts only."""
    return _proof(project_id, requirement_id, evaluation_mode, user)


@router.post("/projects/{project_id}/decision-proof/{requirement_id}")
def post_decision_proof(
    project_id: str,
    requirement_id: str,
    body: DecisionProofRequest,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    """Proof for a hypothetical fact set (e.g. the proposed side of a Change
    Impact diff). Facts are validated against the registry, merged onto a
    copy of the stored facts, labelled HYPOTHETICAL, and never persisted."""
    return _proof(project_id, requirement_id, body.evaluation_mode, user, body.hypothetical_facts)
