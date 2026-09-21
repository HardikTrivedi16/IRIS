from typing import Dict, List, Set, Tuple
from uuid import UUID

from .models import (
    DependencyEdge,
    GraphAnalysis,
    GraphDiff,
    WorkflowStatus,
)


def diff_graphs(old_analysis: GraphAnalysis, new_analysis: GraphAnalysis) -> GraphDiff:
    """
    Computes deterministic structural and workflow diff between two completed graph evaluations.
    
    Invariants:
    1. Node differences: added_requirement_ids and removed_requirement_ids.
    2. Structural edge differences: Edge identity is (prerequisite_id, dependent_id).
       Changes in source_rule_version_id provenance do NOT mark an edge as removed/added.
    3. newly_blocked: Requirements that were not BLOCKED in old (or are newly added) and are now BLOCKED.
    4. newly_unblocked: Requirements that were BLOCKED in old and are now AVAILABLE or INDEPENDENT.
    5. critical_path_changed: True if critical path sequence or duration has changed.
    """
    old_req_ids = {n.requirement_id for n in old_analysis.nodes}
    new_req_ids = {n.requirement_id for n in new_analysis.nodes}

    added_req_ids = tuple(sorted(list(new_req_ids - old_req_ids), key=str))
    removed_req_ids = tuple(sorted(list(old_req_ids - new_req_ids), key=str))

    old_edge_map: Dict[Tuple[UUID, UUID], DependencyEdge] = {e.structural_key: e for e in old_analysis.edges}
    new_edge_map: Dict[Tuple[UUID, UUID], DependencyEdge] = {e.structural_key: e for e in new_analysis.edges}

    old_edge_keys = set(old_edge_map.keys())
    new_edge_keys = set(new_edge_map.keys())

    added_edge_keys = new_edge_keys - old_edge_keys
    removed_edge_keys = old_edge_keys - new_edge_keys

    added_edges = tuple(
        sorted(
            [new_edge_map[k] for k in added_edge_keys],
            key=lambda e: (str(e.prerequisite_requirement_id), str(e.dependent_requirement_id))
        )
    )
    removed_edges = tuple(
        sorted(
            [old_edge_map[k] for k in removed_edge_keys],
            key=lambda e: (str(e.prerequisite_requirement_id), str(e.dependent_requirement_id))
        )
    )

    # Status tracking for newly blocked and unblocked
    old_status_map = {n.requirement_id: n.status for n in old_analysis.nodes}
    new_status_map = {n.requirement_id: n.status for n in new_analysis.nodes}

    newly_blocked_ids: List[UUID] = []
    newly_unblocked_ids: List[UUID] = []

    for req_id, new_status in new_status_map.items():
        old_status = old_status_map.get(req_id)
        if new_status == WorkflowStatus.BLOCKED:
            if old_status != WorkflowStatus.BLOCKED:
                newly_blocked_ids.append(req_id)
        elif old_status == WorkflowStatus.BLOCKED and new_status in (WorkflowStatus.AVAILABLE, WorkflowStatus.INDEPENDENT):
            newly_unblocked_ids.append(req_id)

    newly_blocked_ids.sort(key=str)
    newly_unblocked_ids.sort(key=str)

    # Critical path comparison
    crit_changed = (
        old_analysis.critical_path != new_analysis.critical_path or
        old_analysis.critical_path_duration != new_analysis.critical_path_duration or
        old_analysis.critical_path_available != new_analysis.critical_path_available
    )

    return GraphDiff(
        added_requirement_ids=added_req_ids,
        removed_requirement_ids=removed_req_ids,
        added_edges=added_edges,
        removed_edges=removed_edges,
        newly_blocked_requirement_ids=tuple(newly_blocked_ids),
        newly_unblocked_requirement_ids=tuple(newly_unblocked_ids),
        critical_path_changed=crit_changed,
        previous_critical_path=old_analysis.critical_path,
        current_critical_path=new_analysis.critical_path
    )
