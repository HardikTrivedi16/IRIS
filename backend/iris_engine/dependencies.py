"""
Generic Dependency interface (Phase 7 §6).

Phase 6 state: zero verified DEP-### edges exist; five candidate
relationships are preserved in dependency_review_register.yaml but are NOT
executed. This module implements the interface a future phase's verified
edges would be consumed through — it does not infer, execute, or fabricate
any of the five review candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DependencyResult:
    requirement_id: str
    verified_edges_as_target: list = field(default_factory=list)  # DEP-### this requirement depends on
    verified_edges_as_source: list = field(default_factory=list)  # DEP-### this requirement blocks
    unresolved_candidate_count: int = 0
    note: str = ""


def evaluate_dependencies(requirement_id: str, dataset) -> DependencyResult:
    """Reads dependencies_index.yaml (currently empty) generically — this
    function does not know or care that the count happens to be zero today;
    it will pick up verified edges automatically once a future phase adds
    them to the index, with no code change required here."""
    edges = dataset.dependencies_index.get("dependencies", []) or []
    as_target = [e for e in edges if e.get("to_requirement_id") == requirement_id]
    as_source = [e for e in edges if e.get("from_requirement_id") == requirement_id]

    candidates = dataset.dependency_review_register.get("review_items", []) or []
    # Only counted for visibility in the Decision artifact; never executed.
    relevant_candidates = 0
    for c in candidates:
        rel = c.get("candidate_relationship", "")
        if requirement_id in rel:
            relevant_candidates += 1

    if edges:
        note = f"{len(as_target) + len(as_source)} verified dependency edge(s) found."
    else:
        note = (
            "Zero verified DEP-### edges exist in the current dataset. "
            f"{len(candidates)} candidate relationship(s) are preserved in "
            "dependency_review_register.yaml but were NOT executed."
        )

    return DependencyResult(
        requirement_id=requirement_id,
        verified_edges_as_target=as_target,
        verified_edges_as_source=as_source,
        unresolved_candidate_count=relevant_candidates,
        note=note,
    )
