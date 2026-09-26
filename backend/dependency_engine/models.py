from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from .exceptions import InvalidRequirementError


class RelationshipType(str, Enum):
    PREREQUISITE = "PREREQUISITE"
    # Informational only: never executed as an ordering/critical-path prerequisite.
    REQUIRES_OUTCOME_OF = "REQUIRES_OUTCOME_OF"


class WorkflowStatus(str, Enum):
    BLOCKED = "BLOCKED"
    INDEPENDENT = "INDEPENDENT"
    AVAILABLE = "AVAILABLE"


class ParallelClassification(str, Enum):
    POTENTIALLY_PARALLELISABLE = "POTENTIALLY_PARALLELISABLE"
    NOT_CLASSIFIED = "NOT_CLASSIFIED"


@dataclass(frozen=True)
class ApplicableRequirement:
    """
    Normalized requirement / approval node entering the Dependency Engine.
    All fields are pre-evaluated by the deterministic Rule Engine.
    """
    requirement_id: UUID
    requirement_code: str
    name: str
    rule_version_id: UUID
    parallel_allowed: bool = False
    parallel_constraint: Optional[str] = None
    duration: Optional[int] = None

    def __post_init__(self):
        if self.duration is not None:
            if not isinstance(self.duration, int) or self.duration <= 0:
                raise InvalidRequirementError(
                    f"Requirement duration for '{self.requirement_code}' must be a positive integer (> 0) if supplied; got {self.duration}."
                )


@dataclass(frozen=True)
class DependencyEdge:
    """
    Directed dependency specification: prerequisite -> dependent.
    (dependent requires prerequisite to be satisfied).
    """
    prerequisite_requirement_id: UUID
    dependent_requirement_id: UUID
    relationship_type: RelationshipType = RelationshipType.PREREQUISITE
    source_rule_version_id: Optional[UUID] = None

    @property
    def structural_key(self) -> Tuple[UUID, UUID]:
        """Edge identity for structural comparisons independent of provenance."""
        return (self.prerequisite_requirement_id, self.dependent_requirement_id)


@dataclass(frozen=True)
class IgnoredDependency:
    """
    Captures a configured dependency edge whose endpoint(s) lie outside the current project graph.
    """
    edge: DependencyEdge
    reason: str = "ENDPOINT_OUTSIDE_PROJECT_GRAPH"


@dataclass(frozen=True)
class AnalyzedNode:
    """
    Analyzed workflow node containing state, parallel classification, and explainable prerequisite blockers.
    """
    requirement_id: UUID
    requirement_code: str
    name: str

    status: WorkflowStatus

    parallel_classification: ParallelClassification
    parallel_constraint: Optional[str]

    duration: Optional[int]

    direct_prerequisite_ids: Tuple[UUID, ...]
    unmet_prerequisite_ids: Tuple[UUID, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Rich internal dictionary representation including diagnostic prerequisites."""
        return {
            "requirement_id": str(self.requirement_id),
            "requirement_code": self.requirement_code,
            "name": self.name,
            "status": self.status.value,
            "parallel_classification": self.parallel_classification.value,
            "parallel_constraint": self.parallel_constraint,
            "duration": self.duration,
            "direct_prerequisite_ids": [str(uid) for uid in self.direct_prerequisite_ids],
            "unmet_prerequisite_ids": [str(uid) for uid in self.unmet_prerequisite_ids]
        }

    def to_api_node_dict(self) -> Dict[str, Any]:
        """Exact frozen public API schema representation according to API_CONTRACT.md."""
        return {
            "requirement_id": str(self.requirement_id),
            "requirement_code": self.requirement_code,
            "name": self.name,
            "status": self.status.value,
            "parallel_classification": self.parallel_classification.value,
            "parallel_constraint": self.parallel_constraint,
            "duration": self.duration
        }


@dataclass(frozen=True)
class GraphAnalysis:
    """
    Complete deterministic analysis output of the project dependency graph.
    """
    nodes: Tuple[AnalyzedNode, ...]
    edges: Tuple[DependencyEdge, ...]

    ignored_dependencies: Tuple[IgnoredDependency, ...]

    topological_order: Tuple[UUID, ...]

    critical_path: Tuple[UUID, ...]
    critical_path_duration: Optional[int]
    critical_path_available: bool

    def to_dict(self) -> Dict[str, Any]:
        """Rich internal dictionary containing full diagnostic metadata."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [
                {
                    "prerequisite_requirement_id": str(e.prerequisite_requirement_id),
                    "dependent_requirement_id": str(e.dependent_requirement_id),
                    "relationship_type": e.relationship_type.value,
                    "source_rule_version_id": str(e.source_rule_version_id) if e.source_rule_version_id else None
                }
                for e in self.edges
            ],
            "ignored_dependencies": [
                {
                    "prerequisite_requirement_id": str(i.edge.prerequisite_requirement_id),
                    "dependent_requirement_id": str(i.edge.dependent_requirement_id),
                    "reason": i.reason
                }
                for i in self.ignored_dependencies
            ],
            "topological_order": [str(uid) for uid in self.topological_order],
            "critical_path": [str(uid) for uid in self.critical_path],
            "critical_path_duration": self.critical_path_duration,
            "critical_path_available": self.critical_path_available
        }

    def to_api_dict(self, evaluation_run_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Emits EXACTLY the frozen public dependency graph API contract:
        GET /projects/{project_id}/dependency-graph
        """
        return {
            "evaluation_run_id": str(evaluation_run_id) if evaluation_run_id else None,
            "nodes": [n.to_api_node_dict() for n in self.nodes],
            "edges": [
                {
                    "prerequisite_requirement_id": str(e.prerequisite_requirement_id),
                    "dependent_requirement_id": str(e.dependent_requirement_id),
                    "relationship_type": e.relationship_type.value,
                    "source_rule_version_id": str(e.source_rule_version_id) if e.source_rule_version_id else None
                }
                for e in self.edges
            ],
            "critical_path": [str(uid) for uid in self.critical_path],
            "critical_path_available": self.critical_path_available
        }


@dataclass(frozen=True)
class GraphDiff:
    """
    Represents structural and workflow changes between two completed graph evaluations.
    """
    added_requirement_ids: Tuple[UUID, ...]
    removed_requirement_ids: Tuple[UUID, ...]

    added_edges: Tuple[DependencyEdge, ...]
    removed_edges: Tuple[DependencyEdge, ...]

    newly_blocked_requirement_ids: Tuple[UUID, ...]
    newly_unblocked_requirement_ids: Tuple[UUID, ...]

    critical_path_changed: bool
    previous_critical_path: Tuple[UUID, ...]
    current_critical_path: Tuple[UUID, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "added_requirement_ids": [str(uid) for uid in self.added_requirement_ids],
            "removed_requirement_ids": [str(uid) for uid in self.removed_requirement_ids],
            "added_edges": [
                {
                    "prerequisite_requirement_id": str(e.prerequisite_requirement_id),
                    "dependent_requirement_id": str(e.dependent_requirement_id),
                    "relationship_type": e.relationship_type.value
                }
                for e in self.added_edges
            ],
            "removed_edges": [
                {
                    "prerequisite_requirement_id": str(e.prerequisite_requirement_id),
                    "dependent_requirement_id": str(e.dependent_requirement_id),
                    "relationship_type": e.relationship_type.value
                }
                for e in self.removed_edges
            ],
            "newly_blocked_requirement_ids": [str(uid) for uid in self.newly_blocked_requirement_ids],
            "newly_unblocked_requirement_ids": [str(uid) for uid in self.newly_unblocked_requirement_ids],
            "critical_path_changed": self.critical_path_changed,
            "previous_critical_path": [str(uid) for uid in self.previous_critical_path],
            "current_critical_path": [str(uid) for uid in self.current_critical_path]
        }
