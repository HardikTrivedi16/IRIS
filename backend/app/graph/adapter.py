"""
IRIS -> NetworkX adapter.

    Phase 9 Rule Engine (frozen, unmodified)
        |  engine_service.evaluate_all(project_id, facts, mode)
        v
    list[Decision]  (final_state per requirement, from backend/iris_engine)
        |
        v
    THIS MODULE
        |  - filters to requirements the Rule Engine found APPLICABLE
        |  - maps requirement codes -> stable UUIDs (requirement_mapping.py)
        |  - reads dependencies_index.yaml generically (currently empty;
        |    see iris_engine.dependencies.evaluate_dependencies, which this
        |    module deliberately reuses instead of re-implementing)
        |  - NEVER reads dependency_review_register.yaml candidates as edges
        |  - NEVER reads NetworkX's own mock_data.py
        v
    ApplicableRequirement[] + DependencyEdge[] + requirement_states{}
        |
        v
    dependency_engine.DependencyService.analyze(...)   (unmodified NetworkX package)

This module contains no regulatory logic and makes no legal-applicability
decisions of its own — it only reshapes data the Rule Engine already
produced. If the Rule Engine says a requirement does not apply, or a
decision is BLOCKED/UNKNOWN/REQUIRES_* (anything other than APPLICABLE),
that requirement is not placed in the graph at all: the graph only
organizes work that is actually required, never speculative or blocked
regulatory conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dependency_engine import ApplicableRequirement, DependencyEdge, RelationshipType
from dependency_engine.exceptions import InvalidRequirementError

from iris_engine.dependencies import evaluate_dependencies

from .requirement_mapping import RequirementIdMap

# Decision final_state values that mean "this requirement legally applies
# to this project" per iris_engine.rules / iris_engine.decision. Every
# other final_state (NOT_APPLICABLE, REQUIRES_INFORMATION, REQUIRES_REVIEW,
# UNKNOWN, and every BLOCKED_* engine state) is excluded from the graph —
# the Dependency Engine only organizes confirmed applicable work, it does
# not second-guess or reinterpret an inconclusive Rule Engine result.
APPLICABLE_FINAL_STATES = frozenset({"APPLICABLE"})


@dataclass(frozen=True)
class AdapterResult:
    """Everything DependencyService.analyze() needs, plus the id map to
    translate its UUID-keyed output back into IRIS requirement codes, and
    a transparency record of what was excluded and why."""
    requirements: tuple[ApplicableRequirement, ...]
    dependencies: tuple[DependencyEdge, ...]
    requirement_states: dict[Any, bool]
    id_map: RequirementIdMap
    excluded: tuple[dict, ...]  # [{requirement_id, final_state}] — not applicable, so not graphed
    dependency_note: str  # verbatim note from iris_engine.dependencies (e.g. "zero verified edges")


def _duration_for(requirement_id: str) -> int | None:
    """No verified statutory/legal duration source exists in the current
    Phase 9 dataset (see regulatory-data/requirements/*.yaml — there is no
    duration field). SLA `duration_hours` (backend/app/store/department_store.py)
    is a Government *operational* target, not a legal requirement duration,
    and per the integration brief must never be silently repurposed as one.
    So duration is always None today — this function is the single,
    documented place that would change if/when a verified legal-duration
    source is added to the Requirement catalog."""
    return None


def build_graph_inputs(
    project_id: str,
    decisions: list[dict],
    dataset,
    requirement_satisfaction: dict[str, bool] | None = None,
) -> AdapterResult:
    """
    Parameters
    ----------
    decisions:
        Output of ``engine_service.evaluate_all(project_id, facts, mode)`` —
        a list of Decision dicts, one per requirement in the dataset.
    dataset:
        The loaded ``RegulatoryDataset`` (``engine_service.get_dataset()``),
        used only to resolve each requirement's human-readable ``code`` and
        to read the dependencies index/registers via the existing
        ``iris_engine.dependencies`` module.
    requirement_satisfaction:
        Optional, explicit map of ``requirement_id -> satisfied`` (has the
        project actually obtained/completed this requirement, e.g. via a
        government Application reaching an approved terminal stage).
        IRIS's current data model does not yet expose a single authoritative
        source for this (see Known Limitations in the integration summary),
        so callers that don't have one may omit it entirely; every
        requirement then defaults to *not satisfied*, which fails closed
        (matches ``dependency_engine``'s own default-False-on-missing-state
        behavior) rather than fabricating an "obtained" status.
    """
    requirement_satisfaction = requirement_satisfaction or {}

    id_map = RequirementIdMap()
    applicable_reqs: list[ApplicableRequirement] = []
    requirement_states: dict[Any, bool] = {}
    excluded: list[dict] = []

    by_req_id = {d.get("requirement_id"): d for d in decisions}

    for requirement_id, decision in by_req_id.items():
        final_state = decision.get("final_state")
        if final_state not in APPLICABLE_FINAL_STATES:
            excluded.append({"requirement_id": requirement_id, "final_state": final_state})
            continue

        req_record = dataset.requirements.get(requirement_id) or {}
        code = req_record.get("code") or requirement_id
        title = req_record.get("title") or requirement_id

        req_uuid = id_map.register(requirement_id)
        try:
            applicable_reqs.append(
                ApplicableRequirement(
                    requirement_id=req_uuid,
                    requirement_code=code,
                    name=title,
                    rule_version_id=id_map.register(f"rule-version::{decision.get('rule_version_ids', [None])[0]}")
                    if decision.get("rule_version_ids")
                    else id_map.register(f"rule-version::unknown::{requirement_id}"),
                    parallel_allowed=False,
                    parallel_constraint=None,
                    duration=_duration_for(requirement_id),
                )
            )
        except InvalidRequirementError:
            # Fails closed: a malformed requirement is excluded from the
            # graph rather than raising a 500 for the whole project.
            excluded.append({"requirement_id": requirement_id, "final_state": final_state, "error": "invalid_requirement"})
            continue

        requirement_states[req_uuid] = bool(requirement_satisfaction.get(requirement_id, False))

    # --- Dependencies: reuse the existing, unmodified dependencies module.
    # It reads dependencies_index.yaml generically (empty today) and will
    # pick up future verified DEP-### edges automatically with no adapter
    # change. It never reads dependency_review_register.yaml candidates as
    # real edges, and this adapter does not either.
    dependency_edges: list[DependencyEdge] = []
    dep_note = ""
    seen_edge_ids: set[str] = set()
    for requirement_id in by_req_id:
        if id_map.uuid_for(requirement_id) is None:
            continue  # not an applicable node; an edge touching it would be a phantom node
        dep_result = evaluate_dependencies(requirement_id, dataset)
        dep_note = dep_result.note  # same note text across all requirements today (index is empty)
        for edge in dep_result.verified_edges_as_source:
            _maybe_add_edge(edge, id_map, dependency_edges, seen_edge_ids)
        for edge in dep_result.verified_edges_as_target:
            _maybe_add_edge(edge, id_map, dependency_edges, seen_edge_ids)

    return AdapterResult(
        requirements=tuple(applicable_reqs),
        dependencies=tuple(dependency_edges),
        requirement_states=requirement_states,
        id_map=id_map,
        excluded=tuple(excluded),
        dependency_note=dep_note or "No requirements evaluated as applicable; dependency index not consulted.",
    )


def _maybe_add_edge(
    edge: dict,
    id_map: RequirementIdMap,
    out: list[DependencyEdge],
    seen: set[str],
) -> None:
    """Translate one verified DEP-### edge record (dependencies_index.yaml
    schema: from_requirement_id / to_requirement_id) into a DependencyEdge,
    but ONLY if both endpoints are requirements already in this project's
    applicable-requirement set. An edge with either endpoint outside the
    graph is silently dropped here (not fabricated as an IgnoredDependency
    at this layer) — DependencyService itself also enforces this via
    IgnoredDependency for edges that slip through, so this is
    belt-and-braces, not the only safeguard."""
    from_id = edge.get("from_requirement_id")
    to_id = edge.get("to_requirement_id")
    if not from_id or not to_id:
        return
    key = f"{from_id}->{to_id}"
    if key in seen:
        return
    prereq_uuid = id_map.uuid_for(from_id)
    dependent_uuid = id_map.uuid_for(to_id)
    if prereq_uuid is None or dependent_uuid is None:
        return
    seen.add(key)
    source_rv = edge.get("source_rule_version_id")
    out.append(
        DependencyEdge(
            prerequisite_requirement_id=prereq_uuid,
            dependent_requirement_id=dependent_uuid,
            relationship_type=RelationshipType.PREREQUISITE,
            source_rule_version_id=id_map.register(f"rule-version::{source_rv}") if source_rv else None,
        )
    )
