"""
Project dependency graph endpoints (Phase 2/3 of the NetworkX integration).

    GET  /api/v1/projects/{project_id}/dependency-graph
    POST /api/v1/projects/{project_id}/dependency-graph/impact

Authorization is delegated entirely to the existing ``get_project`` (from
``routers.projects``) — the same tenant-isolation/demo-mode/role logic
already enforced for every other project sub-resource
(``/projects/{id}/facts``, ``/projects/{id}/documents``, ...). This router
adds no new authorization behavior.

Uses request-body / stored facts exactly like ``/evaluate``: this router
never talks to ``dependency_engine`` directly (see ``app/graph/__init__.py``)
and never fabricates dependency edges, durations, or requirement states —
all of that is the adapter's job (``app/graph/adapter.py``), which is
deliberately conservative per the integration brief.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..graph.schemas import GraphImpactRequest
from ..graph.service import get_project_dependency_graph, get_project_dependency_graph_diff
from ..security import CurrentUser, get_optional_user
from ..store.base import StoreError
from .evaluate import _merged_facts
from .projects import get_project

logger = logging.getLogger("iris.api.dependency_graph")
router = APIRouter(prefix="/api/v1", tags=["dependency-graph"])


@router.get("/projects/{project_id}/dependency-graph")
def get_dependency_graph(
    project_id: str,
    evaluation_mode: str = "PRODUCTION",
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    # Reuses the exact same authorization/tenant-isolation check as every
    # other /projects/{id}/* endpoint — raises 401/404 as appropriate.
    get_project(project_id, user=user)

    facts = _merged_facts(project_id, {})
    try:
        return get_project_dependency_graph(
            project_id=project_id, facts=facts, evaluation_mode=evaluation_mode
        )
    except StoreError as exc:
        logger.error("Persistence error building dependency graph for %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable")
    except Exception as exc:  # fail safe — never leak internals
        logger.exception("Dependency graph build failed for %s", project_id)
        raise HTTPException(status_code=500, detail="Dependency graph build failed") from exc


@router.post("/projects/{project_id}/dependency-graph/impact")
def get_dependency_graph_impact(
    project_id: str,
    body: GraphImpactRequest,
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> dict:
    """Phase 3: compares two authoritative IRIS-generated graphs for the
    SAME project (e.g. facts before/after a document extraction or a
    project edit) and returns the structural/workflow diff. Both graphs are
    always freshly generated from the live Phase 9 evaluator — this never
    reads a stored graph snapshot or a NetworkX mock fixture."""
    get_project(project_id, user=user)

    old_facts = _merged_facts(project_id, body.old_facts)
    new_facts = _merged_facts(project_id, body.new_facts)
    try:
        return get_project_dependency_graph_diff(
            project_id=project_id,
            old_facts=old_facts,
            new_facts=new_facts,
            evaluation_mode=body.evaluation_mode,
        )
    except StoreError as exc:
        logger.error("Persistence error building graph diff for %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail="Persistence backend is unavailable")
    except Exception as exc:
        logger.exception("Dependency graph diff failed for %s", project_id)
        raise HTTPException(status_code=500, detail="Dependency graph diff failed") from exc
