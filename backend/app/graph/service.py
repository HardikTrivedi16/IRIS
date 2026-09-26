"""
Orchestrates: Phase 9 decisions -> adapter -> DependencyService.analyze()
-> IRIS domain response models.

Never returns a raw ``dependency_engine`` object (UUID, dataclass, or
``nx.DiGraph``) through the API — every UUID is resolved back to its IRIS
requirement code via the ``RequirementIdMap`` built alongside it, per the
integration brief ("Do NOT expose raw NetworkX objects through the API.
Use domain response models.").
"""
from __future__ import annotations

from dependency_engine import dependency_service
from dependency_engine.diff import diff_graphs
from dependency_engine.models import GraphAnalysis, GraphDiff

from .. import engine_service
from .adapter import build_graph_inputs, AdapterResult
from .requirement_mapping import RequirementIdMap


def _resolve(u, id_map: RequirementIdMap) -> str:
    code = id_map.code_for(u)
    return code if code is not None else str(u)


def _node_to_domain(node, id_map: RequirementIdMap) -> dict:
    return {
        "requirement_id": _resolve(node.requirement_id, id_map),
        "requirement_code": node.requirement_code,
        "name": node.name,
        "status": node.status.value,
        "parallel_classification": node.parallel_classification.value,
        "parallel_constraint": node.parallel_constraint,
        "duration": node.duration,
        "direct_prerequisite_ids": [_resolve(p, id_map) for p in node.direct_prerequisite_ids],
        "unmet_prerequisite_ids": [_resolve(p, id_map) for p in node.unmet_prerequisite_ids],
    }


def _edge_to_domain(edge, id_map: RequirementIdMap) -> dict:
    return {
        "prerequisite_requirement_id": _resolve(edge.prerequisite_requirement_id, id_map),
        "dependent_requirement_id": _resolve(edge.dependent_requirement_id, id_map),
        "relationship_type": edge.relationship_type.value,
    }


def _analysis_to_domain(analysis: GraphAnalysis, adapter: AdapterResult) -> dict:
    id_map = adapter.id_map
    return {
        "nodes": [_node_to_domain(n, id_map) for n in analysis.nodes],
        "edges": [_edge_to_domain(e, id_map) for e in analysis.edges],
        "ignored_dependencies": [
            {
                "prerequisite_requirement_id": _resolve(i.edge.prerequisite_requirement_id, id_map),
                "dependent_requirement_id": _resolve(i.edge.dependent_requirement_id, id_map),
                "reason": i.reason,
            }
            for i in analysis.ignored_dependencies
        ],
        "topological_order": [_resolve(u, id_map) for u in analysis.topological_order],
        "critical_path": [_resolve(u, id_map) for u in analysis.critical_path],
        "critical_path_duration": analysis.critical_path_duration,
        "critical_path_available": analysis.critical_path_available,
        "excluded_requirements": list(adapter.excluded),
        "dependency_data_note": adapter.dependency_note,
        "diagnostic_relationships": list(adapter.diagnostic_relationships),
        "relationships": list(adapter.relationships),
    }


def get_project_dependency_graph(
    project_id: str,
    facts: dict,
    evaluation_mode: str = "PRODUCTION",
    requirement_satisfaction: dict[str, bool] | None = None,
) -> dict:
    """Runs the frozen Phase 9 evaluator for every requirement, adapts the
    applicable subset into the NetworkX graph engine's input types, and
    returns a JSON-serializable domain response — never a raw
    ``dependency_engine`` object."""
    dataset = engine_service.get_dataset()
    decisions = engine_service.evaluate_all(
        project_id=project_id, project_facts=facts, evaluation_mode=evaluation_mode
    )
    adapter_result = build_graph_inputs(
        project_id=project_id,
        decisions=decisions,
        dataset=dataset,
        requirement_satisfaction=requirement_satisfaction,
    )
    analysis = dependency_service.analyze(
        requirements=adapter_result.requirements,
        dependencies=adapter_result.dependencies,
        requirement_states=adapter_result.requirement_states,
    )
    return _analysis_to_domain(analysis, adapter_result)


def get_project_dependency_graph_diff(
    project_id: str,
    old_facts: dict,
    new_facts: dict,
    evaluation_mode: str = "PRODUCTION",
    requirement_satisfaction: dict[str, bool] | None = None,
) -> dict:
    """Phase 3 (Impact Recalculation): evaluates the SAME project under two
    fact sets (e.g. project facts before/after a document extraction or a
    project-detail edit), builds two authoritative IRIS-generated graphs,
    and diffs them. Never compares against NetworkX mock fixtures — both
    graphs always come from ``get_project_dependency_graph`` above, which
    only ever consumes live Phase 9 evaluator output."""
    dataset = engine_service.get_dataset()

    old_decisions = engine_service.evaluate_all(project_id=project_id, project_facts=old_facts, evaluation_mode=evaluation_mode)
    new_decisions = engine_service.evaluate_all(project_id=project_id, project_facts=new_facts, evaluation_mode=evaluation_mode)

    old_adapter = build_graph_inputs(project_id, old_decisions, dataset, requirement_satisfaction)
    new_adapter = build_graph_inputs(project_id, new_decisions, dataset, requirement_satisfaction)

    old_analysis = dependency_service.analyze(
        requirements=old_adapter.requirements,
        dependencies=old_adapter.dependencies,
        requirement_states=old_adapter.requirement_states,
    )
    new_analysis = dependency_service.analyze(
        requirements=new_adapter.requirements,
        dependencies=new_adapter.dependencies,
        requirement_states=new_adapter.requirement_states,
    )

    diff: GraphDiff = diff_graphs(old_analysis, new_analysis)
    # Resolve against the union of both id maps (a requirement code maps to
    # the same UUID in both, since the mapping is a pure function of the
    # code — see requirement_mapping.py — so either map alone would work;
    # union is just defensive in case one side has requirements the other
    # doesn't).
    union_map = RequirementIdMap()
    for code in list(old_adapter.id_map._code_to_uuid.keys()) + list(new_adapter.id_map._code_to_uuid.keys()):
        union_map.register(code)

    return {
        "added_requirement_ids": [_resolve(u, union_map) for u in diff.added_requirement_ids],
        "removed_requirement_ids": [_resolve(u, union_map) for u in diff.removed_requirement_ids],
        "added_edges": [_edge_to_domain(e, union_map) for e in diff.added_edges],
        "removed_edges": [_edge_to_domain(e, union_map) for e in diff.removed_edges],
        "newly_blocked_requirement_ids": [_resolve(u, union_map) for u in diff.newly_blocked_requirement_ids],
        "newly_unblocked_requirement_ids": [_resolve(u, union_map) for u in diff.newly_unblocked_requirement_ids],
        "critical_path_changed": diff.critical_path_changed,
        "previous_critical_path": [_resolve(u, union_map) for u in diff.previous_critical_path],
        "current_critical_path": [_resolve(u, union_map) for u in diff.current_critical_path],
    }
