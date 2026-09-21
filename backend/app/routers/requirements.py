from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import engine_service

router = APIRouter(prefix="/api/v1", tags=["requirements"])


@router.get("/requirements")
def list_requirements() -> list[dict]:
    return engine_service.list_requirements()


@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: str) -> dict:
    req = engine_service.get_requirement(requirement_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Requirement {requirement_id} not found in dataset")
    return req
