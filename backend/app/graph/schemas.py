from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GraphImpactRequest(BaseModel):
    """Body for POST /projects/{project_id}/dependency-graph/impact.

    ``old_facts``/``new_facts`` are merged on top of the project's stored
    facts exactly like ``/evaluate`` does (request wins on key collision) —
    this endpoint does not introduce a second facts-merging behavior.
    """
    old_facts: dict[str, Any] = Field(default_factory=dict)
    new_facts: dict[str, Any] = Field(default_factory=dict)
    evaluation_mode: Literal["PRODUCTION", "NON_PRODUCTION"] = "PRODUCTION"
