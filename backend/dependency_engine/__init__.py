"""
IRIS — Dependency & Workflow Graph Engine
Authoritative standalone package for deterministic regulatory dependency analysis.
"""

from .models import (
    ApplicableRequirement,
    DependencyEdge,
    RelationshipType,
    WorkflowStatus,
    ParallelClassification,
    AnalyzedNode,
    GraphAnalysis,
    GraphDiff,
    IgnoredDependency,
)
from .dag_engine import DependencyService, dependency_service
from .diff import diff_graphs
from .exceptions import (
    DependencyEngineError,
    InvalidRequirementError,
    InvalidDependencyError,
    DuplicateRequirementError,
    DuplicateDependencyError,
    SelfDependencyError,
    DependencyCycleError,
    RequirementNotFoundError,
)

__all__ = [
    "ApplicableRequirement",
    "DependencyEdge",
    "RelationshipType",
    "WorkflowStatus",
    "ParallelClassification",
    "AnalyzedNode",
    "GraphAnalysis",
    "GraphDiff",
    "IgnoredDependency",
    "DependencyService",
    "dependency_service",
    "diff_graphs",
    "DependencyEngineError",
    "InvalidRequirementError",
    "InvalidDependencyError",
    "DuplicateRequirementError",
    "DuplicateDependencyError",
    "SelfDependencyError",
    "DependencyCycleError",
    "RequirementNotFoundError",
]
