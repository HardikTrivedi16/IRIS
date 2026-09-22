"""
Project Fact schema endpoints — what the engine can actually be asked.

    GET /api/v1/facts/registry
    GET /api/v1/requirements/{requirement_id}/required-facts

Both are derived read-only from the frozen regulatory dataset (see
``app/fact_registry.py``). They author nothing: every key, unit, referenced
comparison value and rule/requirement link is copied from the dataset's own
Conditions and Rule Versions.

These power two UI surfaces that must stay generic as verified regulatory
content is added:

  * the fact-capture step of project creation (ask only for facts a Rule
    Version genuinely declares in ``required_project_facts``), and
  * the change-impact fact editor (offer only facts that can actually move
    a decision, typed correctly).

No authentication is required: the response contains regulatory *schema*
(which questions the rules ask), never any project's answers. This matches
the existing unauthenticated ``/api/v1/requirements`` and ``/api/v1/engine``
endpoints, which expose the same dataset.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import engine_service
from ..fact_registry import build_fact_registry, required_facts_for_requirement

router = APIRouter(prefix="/api/v1", tags=["facts"])

_DERIVATION_NOTE = (
    "Derived from the regulatory dataset's own Conditions/Rule Versions and "
    "the scheme catalogue's own Scheme Conditions/Schemes — one shared "
    "Project Fact vocabulary for both. 'values_referenced_by_conditions' "
    "(alias: 'values_referenced_by_rules') lists the comparison values "
    "those records mention — it is not an exhaustive or legally "
    "authoritative list of permitted values."
)


@router.get("/facts/registry")
def get_fact_registry() -> dict:
    return {
        "facts": list(build_fact_registry()),
        "note": _DERIVATION_NOTE,
    }


@router.get("/requirements/{requirement_id}/required-facts")
def get_required_facts(requirement_id: str) -> dict:
    if engine_service.get_requirement(requirement_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Requirement {requirement_id} not found in dataset",
        )
    return {
        "requirement_id": requirement_id,
        "facts": required_facts_for_requirement(requirement_id),
        "note": _DERIVATION_NOTE,
    }
