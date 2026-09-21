from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from uuid import UUID
import networkx as nx

from .models import (
    ApplicableRequirement,
    DependencyEdge,
    IgnoredDependency,
    AnalyzedNode,
    GraphAnalysis,
    WorkflowStatus,
    ParallelClassification,
)
from .exceptions import (
    DuplicateRequirementError,
    DuplicateDependencyError,
    SelfDependencyError,
    DependencyCycleError,
    RequirementNotFoundError,
)
from .critical_path import (
    calculate_critical_path,
    canonical_node_key,
    canonical_path_key,
)


class DependencyService:
    """
    Authoritative IRIS Dependency & Workflow Graph Engine.
    
    Architectural Boundaries:
    1. GRAPHS ORGANISE — does NOT determine legal applicability (the Rule Engine has already done that).
    2. Reasons over requirements already supplied.
    3. Derived in-memory representation with zero side-effects.
    4. Deterministic lexical tie-breaking.
    5. Fails closed on missing duration or missing satisfaction state.
    """

    def _build_validated_project_graph(
        self,
        requirements: Sequence[ApplicableRequirement],
        dependencies: Sequence[DependencyEdge]
    ) -> Tuple[nx.DiGraph, Dict[UUID, ApplicableRequirement], List[DependencyEdge], List[IgnoredDependency]]:
        """
        Unified internal graph construction helper.
        Enforces:
        - Requirement uniqueness (ID and Code)
        - Explicit project-node addition (no phantom nodes)
        - Outside endpoint filtering into IgnoredDependency
        - Self-dependency rejection
        - Duplicate dependency rejection
        - Cycle detection and validation
        - Deterministic canonical edge sorting
        """
        req_map: Dict[UUID, ApplicableRequirement] = {}
        seen_codes: Set[str] = set()

        for req in requirements:
            if req.requirement_id in req_map:
                raise DuplicateRequirementError(
                    f"Duplicate requirement ID detected: {req.requirement_id}",
                    requirement_id=req.requirement_id,
                    requirement_code=req.requirement_code
                )
            if req.requirement_code in seen_codes:
                raise DuplicateRequirementError(
                    f"Duplicate requirement code detected: '{req.requirement_code}'",
                    requirement_id=req.requirement_id,
                    requirement_code=req.requirement_code
                )
            req_map[req.requirement_id] = req
            seen_codes.add(req.requirement_code)

        graph = nx.DiGraph()
        for req_id, req in req_map.items():
            graph.add_node(
                req_id,
                requirement_id=req_id,
                requirement_code=req.requirement_code,
                name=req.name,
                duration=req.duration
            )

        included_edges: List[DependencyEdge] = []
        ignored_deps: List[IgnoredDependency] = []
        seen_edge_keys: Set[Tuple[UUID, UUID]] = set()

        for dep in dependencies:
            prereq_id = dep.prerequisite_requirement_id
            dep_id = dep.dependent_requirement_id

            if prereq_id == dep_id:
                raise SelfDependencyError(
                    f"Self-dependency detected for requirement '{prereq_id}'. A requirement cannot depend on itself.",
                    requirement_id=prereq_id
                )

            structural_key = dep.structural_key
            if structural_key in seen_edge_keys:
                raise DuplicateDependencyError(
                    f"Duplicate dependency edge detected: {prereq_id} -> {dep_id}",
                    prerequisite_id=prereq_id,
                    dependent_id=dep_id
                )
            seen_edge_keys.add(structural_key)

            if prereq_id in req_map and dep_id in req_map:
                graph.add_edge(prereq_id, dep_id, edge=dep)
                included_edges.append(dep)
            else:
                ignored_deps.append(
                    IgnoredDependency(
                        edge=dep,
                        reason="ENDPOINT_OUTSIDE_PROJECT_GRAPH"
                    )
                )

        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            raise DependencyCycleError(
                f"Circular regulatory dependency detected in graph: {cycles}",
                cycles=cycles
            )

        # Deterministically sort included edges and ignored dependencies
        included_edges.sort(
            key=lambda e: (
                canonical_node_key(e.prerequisite_requirement_id, req_map),
                canonical_node_key(e.dependent_requirement_id, req_map)
            )
        )
        ignored_deps.sort(
            key=lambda i: (
                str(i.edge.prerequisite_requirement_id),
                str(i.edge.dependent_requirement_id)
            )
        )

        return graph, req_map, included_edges, ignored_deps

    def analyze(
        self,
        requirements: Sequence[ApplicableRequirement],
        dependencies: Sequence[DependencyEdge],
        requirement_states: Mapping[UUID, bool],
    ) -> GraphAnalysis:
        """
        Builds and analyzes the project-specific workflow DAG.
        """
        # Step 1: Handle empty graph case cleanly
        if len(requirements) == 0:
            return GraphAnalysis(
                nodes=(),
                edges=(),
                ignored_dependencies=(),
                topological_order=(),
                critical_path=(),
                critical_path_duration=None,
                critical_path_available=False
            )

        # Step 2: Build validated project graph via single canonical helper
        graph, req_map, included_edges, ignored_deps = self._build_validated_project_graph(
            requirements=requirements,
            dependencies=dependencies
        )

        # Step 3: Deterministic lexical topological ordering
        topo_order = tuple(
            nx.lexicographical_topological_sort(
                graph,
                key=lambda uid: canonical_node_key(uid, req_map)
            )
        )

        # Step 4: Analyze nodes for workflow status, parallel classification, and unmet prerequisites
        sorted_node_ids = sorted(list(graph.nodes), key=lambda uid: canonical_node_key(uid, req_map))
        analyzed_nodes: List[AnalyzedNode] = []

        for uid in sorted_node_ids:
            req = req_map[uid]
            
            # Direct prerequisites in canonical order
            direct_prereqs = tuple(
                sorted(
                    list(graph.predecessors(uid)),
                    key=lambda p: canonical_node_key(p, req_map)
                )
            )

            # Unmet prerequisites check (missing satisfaction state treated as False / NOT SATISFIED)
            unmet_prereqs = tuple(
                p for p in direct_prereqs
                if not bool(requirement_states.get(p, False))
            )

            # Workflow status determination
            if len(direct_prereqs) == 0:
                status = WorkflowStatus.INDEPENDENT
            elif len(unmet_prereqs) > 0:
                status = WorkflowStatus.BLOCKED
            else:
                status = WorkflowStatus.AVAILABLE

            # Parallel classification (strictly based on explicit metadata)
            if req.parallel_allowed:
                parallel_class = ParallelClassification.POTENTIALLY_PARALLELISABLE
            else:
                parallel_class = ParallelClassification.NOT_CLASSIFIED

            analyzed_nodes.append(
                AnalyzedNode(
                    requirement_id=uid,
                    requirement_code=req.requirement_code,
                    name=req.name,
                    status=status,
                    parallel_classification=parallel_class,
                    parallel_constraint=req.parallel_constraint,
                    duration=req.duration,
                    direct_prerequisite_ids=direct_prereqs,
                    unmet_prerequisite_ids=unmet_prereqs
                )
            )

        # Step 5: Critical Path Calculation
        crit_path, crit_duration, crit_available = calculate_critical_path(
            graph=graph,
            requirements_map=req_map,
            topological_order=topo_order
        )

        return GraphAnalysis(
            nodes=tuple(analyzed_nodes),
            edges=tuple(included_edges),
            ignored_dependencies=tuple(ignored_deps),
            topological_order=topo_order,
            critical_path=crit_path,
            critical_path_duration=crit_duration,
            critical_path_available=crit_available
        )

    def get_direct_prerequisites(
        self,
        graph: nx.DiGraph,
        requirement_id: UUID,
        req_map: Dict[UUID, ApplicableRequirement]
    ) -> Tuple[UUID, ...]:
        """Returns direct prerequisites of a requirement in canonical order."""
        if requirement_id not in graph:
            raise RequirementNotFoundError(f"Requirement '{requirement_id}' not found in graph.", requirement_id=requirement_id)
        return tuple(
            sorted(
                list(graph.predecessors(requirement_id)),
                key=lambda p: canonical_node_key(p, req_map)
            )
        )

    def get_transitive_prerequisites(
        self,
        graph: nx.DiGraph,
        requirement_id: UUID,
        req_map: Dict[UUID, ApplicableRequirement]
    ) -> Tuple[UUID, ...]:
        """Returns all transitive upstream ancestors in canonical order."""
        if requirement_id not in graph:
            raise RequirementNotFoundError(f"Requirement '{requirement_id}' not found in graph.", requirement_id=requirement_id)
        return tuple(
            sorted(
                list(nx.ancestors(graph, requirement_id)),
                key=lambda p: canonical_node_key(p, req_map)
            )
        )

    def get_dependency_chains(
        self,
        requirements: Sequence[ApplicableRequirement],
        dependencies: Sequence[DependencyEdge],
        target_requirement_id: UUID
    ) -> List[Tuple[UUID, ...]]:
        """
        Computes all simple directed paths starting from any upstream root node
        and ending at target_requirement_id in deterministic order.
        Uses the single unified graph construction pipeline.
        """
        if len(requirements) == 0:
            raise RequirementNotFoundError(
                f"Target requirement '{target_requirement_id}' not found in requirements.",
                requirement_id=target_requirement_id
            )

        graph, req_map, _, _ = self._build_validated_project_graph(
            requirements=requirements,
            dependencies=dependencies
        )

        if target_requirement_id not in req_map:
            raise RequirementNotFoundError(
                f"Target requirement '{target_requirement_id}' not found in requirements.",
                requirement_id=target_requirement_id
            )

        # Roots are nodes with in-degree 0 that can reach target_requirement_id
        ancestors = nx.ancestors(graph, target_requirement_id) | {target_requirement_id}
        roots = [n for n in graph.nodes if graph.in_degree(n) == 0 and n in ancestors]

        all_chains: List[Tuple[UUID, ...]] = []
        for root in roots:
            for path in nx.all_simple_paths(graph, source=root, target=target_requirement_id):
                all_chains.append(tuple(path))

        all_chains.sort(key=lambda p: canonical_path_key(p, req_map))
        return all_chains


# Canonical singleton instance
dependency_service = DependencyService()
