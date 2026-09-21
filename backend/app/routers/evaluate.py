from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .. import engine_service
from ..schemas import EvaluateRequest, EvaluateAllRequest
from ..store import get_store
from ..store.base import StoreError, DecisionConflictError

logger = logging.getLogger("iris.api.evaluate")
router = APIRouter(prefix="/api/v1", tags=["evaluate"])


def _merged_facts(project_id: str, override: dict) -> dict:
    """Stored project facts (if the project exists in the store) merged
    with request-body facts, which win on key collision. A project_id that
    doesn't exist in the store is not an error here — evaluation is a pure
    function of (requirement_id, facts); it degrades to using only the
    facts supplied in the request body."""
    stored = {}
    try:
        if get_store().get_project(project_id) is not None:
            stored = get_store().get_project_facts(project_id)
    except StoreError as exc:
        logger.warning("Could not load stored facts for %s: %s", project_id, exc)
    return {**stored, **override}


def _should_persist(body_persist, evaluation_mode: str) -> bool:
    """Fix 4 — Lazy NON_PRODUCTION evaluation.

    The ``persist`` field in the request schema is tri-state (None / True /
    False). None means "use the default for this mode":
      * PRODUCTION  → default True  (every production decision is stored)
      * NON_PRODUCTION → default False (diagnostics are lazy; only stored
        when the caller explicitly says ``persist: true``)

    This prevents diagnostic evaluations from bloating the audit log and
    matches the Phase 9 intent that NON_PRODUCTION results are clearly
    non-authoritative and should not be automatically persisted.
    """
    if body_persist is not None:
        return bool(body_persist)
    # Default: persist production results, don't auto-persist diagnostics.
    return evaluation_mode == "PRODUCTION"


def _persist(decision: dict, project_facts: dict) -> dict:
    try:
        record = get_store().save_decision(decision, project_facts)
        return {"stored": True, "decision_id": decision["decision_id"], "record": record}
    except DecisionConflictError as exc:
        # A genuine immutability violation is a client-visible error, not a
        # silently-swallowed warning: it means the same decision_id was
        # asked to represent two different semantic Decisions.
        raise HTTPException(status_code=409, detail=str(exc))
    except StoreError as exc:
        logger.error("Failed to persist decision %s: %s", decision.get("decision_id"), exc)
        return {"stored": False, "error": "persistence backend unavailable"}


@router.post("/evaluate")
def evaluate(body: EvaluateRequest) -> dict:
    facts = _merged_facts(body.project_id, body.facts)
    try:
        decision = engine_service.evaluate_requirement(
            project_id=body.project_id,
            requirement_id=body.requirement_id,
            project_facts=facts,
            evaluation_mode=body.evaluation_mode,
        )
    except Exception as exc:  # engine failure — fail safe, never leak internals
        logger.exception("Engine evaluation failed for %s/%s", body.project_id, body.requirement_id)
        raise HTTPException(status_code=500, detail="Engine evaluation failed") from exc

    result: dict = {"decision": decision}
    if _should_persist(body.persist, body.evaluation_mode):
        result["persistence"] = _persist(decision, facts)
    return result


@router.post("/evaluate/all")
def evaluate_all(body: EvaluateAllRequest) -> dict:
    facts = _merged_facts(body.project_id, body.facts)
    try:
        decisions = engine_service.evaluate_all(
            project_id=body.project_id,
            project_facts=facts,
            evaluation_mode=body.evaluation_mode,
        )
    except Exception as exc:
        logger.exception("Engine evaluate_all failed for %s", body.project_id)
        raise HTTPException(status_code=500, detail="Engine evaluation failed") from exc

    result = {"decisions": decisions}
    if _should_persist(body.persist, body.evaluation_mode):
        result["persistence"] = [_persist(d, facts) for d in decisions]
    return result
