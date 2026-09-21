from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID
import networkx as nx

from .models import ApplicableRequirement


def canonical_node_key(node_id: UUID, req_map: Dict[UUID, ApplicableRequirement]) -> Tuple[str, str]:
    """Canonical tie-breaking key for deterministic sorting: (requirement_code, str(UUID))."""
    req = req_map.get(node_id)
    code = req.requirement_code if req else str(node_id)
    return (code, str(node_id))


def canonical_path_key(path: Sequence[UUID], req_map: Dict[UUID, ApplicableRequirement]) -> Tuple[Tuple[str, str], ...]:
    """Canonical path tie-breaking key."""
    return tuple(canonical_node_key(n, req_map) for n in path)


def calculate_critical_path(
    graph: nx.DiGraph,
    requirements_map: Dict[UUID, ApplicableRequirement],
    topological_order: Sequence[UUID]
) -> Tuple[Tuple[UUID, ...], Optional[int], bool]:
    """
    Computes the longest duration path in the DAG using Dynamic Programming on node durations.
    
    Invariants:
    1. Critical path is available ONLY when the graph is non-empty and EVERY node in the graph
       has an explicit positive duration (duration > 0).
    2. If ANY node has duration=None, critical path calculation fails closed:
       returns ((), None, False).
    3. Tie-breaking between equal length longest paths is strictly deterministic using canonical_path_key.
    """
    if graph.number_of_nodes() == 0:
        return (), None, False

    # Check that EVERY node in graph has a positive duration
    for node_id in graph.nodes:
        req = requirements_map.get(node_id)
        if req is None or req.duration is None:
            return (), None, False

    # Dynamic Programming over the precomputed topological order
    # dist[u] stores the maximum cumulative duration from any source root ending at node u
    # path[u] stores the sequence of node UUIDs along that optimal path
    dist: Dict[UUID, int] = {}
    path_map: Dict[UUID, Tuple[UUID, ...]] = {}

    for u in topological_order:
        u_duration = requirements_map[u].duration or 0
        preds = list(graph.predecessors(u))

        if not preds:
            # Root node (in-degree 0)
            dist[u] = u_duration
            path_map[u] = (u,)
        else:
            # Find candidate predecessors that maximize cumulative distance
            # For equal distances, tie-break canonically using the predecessor path's canonical key
            candidate_preds: List[Tuple[int, Tuple[Tuple[str, str], ...], UUID]] = []
            for p in preds:
                p_dist = dist[p]
                p_path = path_map[p]
                candidate_preds.append((p_dist, canonical_path_key(p_path, requirements_map), p))

            # Sort candidate predecessors: highest distance first, then lowest canonical key (lexicographical)
            candidate_preds.sort(key=lambda x: (-x[0], x[1]))
            best_pred_dist, _, best_p = candidate_preds[0]

            dist[u] = best_pred_dist + u_duration
            path_map[u] = path_map[best_p] + (u,)

    # Find the global maximum path across all nodes
    all_candidates: List[Tuple[int, Tuple[Tuple[str, str], ...], Tuple[UUID, ...]]] = []
    for u in graph.nodes:
        u_dist = dist[u]
        u_path = path_map[u]
        all_candidates.append((u_dist, canonical_path_key(u_path, requirements_map), u_path))

    # Sort globally: highest duration first, then deterministic canonical path key
    all_candidates.sort(key=lambda x: (-x[0], x[1]))
    max_duration, _, optimal_path = all_candidates[0]

    return optimal_path, max_duration, True
