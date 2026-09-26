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

#: Executable by the dependency/critical-path engine (when VERIFIED).
EXECUTABLE_DEPENDENCY_TYPES = frozenset({"PREREQUISITE"})
#: Informational only -- never an ordering prerequisite.
INFORMATIONAL_DEPENDENCY_TYPES = frozenset({"REQUIRES_OUTCOME_OF"})

TRUST_VERIFIED = "VERIFIED"
TRUST_DIAGNOSTIC = "DIAGNOSTIC"


def dependency_trust(edge: dict, dataset) -> str:
    """Derived trust (single source of truth = the Verification contract).

    VERIFIED only for a non-informational edge that has an
    APPROVED human DEPENDENCY_EDGE Verification record. Everything else --
    including every REQUIRES_OUTCOME_OF edge -- is DIAGNOSTIC."""
    if edge.get("dependency_type") in INFORMATIONAL_DEPENDENCY_TYPES:
        return TRUST_DIAGNOSTIC
    dep_id = edge.get("dependency_id")
    for ver in (getattr(dataset, "verifications", None) or {}).values():
        if (
            ver.get("target_type") == "DEPENDENCY_EDGE"
            and ver.get("target_id") == dep_id
            and ver.get("result") == "APPROVED"
        ):
            return TRUST_VERIFIED
    return TRUST_DIAGNOSTIC


@dataclass
class DependencyResult:
    requirement_id: str
    verified_edges_as_target: list = field(default_factory=list)  # DEP-### this requirement depends on
    verified_edges_as_source: list = field(default_factory=list)  # DEP-### this requirement blocks
    diagnostic_edges_as_target: list = field(default_factory=list)  # authored, not VERIFIED (incl. informational)
    diagnostic_edges_as_source: list = field(default_factory=list)
    unresolved_candidate_count: int = 0
    note: str = ""


def evaluate_dependencies(requirement_id: str, dataset) -> DependencyResult:
    """Reads dependencies_index.yaml (currently empty) generically — this
    function does not know or care that the count happens to be zero today;
    it will pick up verified edges automatically once a future phase adds
    them to the index, with no code change required here."""
    edges = dataset.dependencies_index.get("dependencies", []) or []
    all_target = [e for e in edges if e.get("to_requirement_id") == requirement_id]
    all_source = [e for e in edges if e.get("from_requirement_id") == requirement_id]
    as_target = [e for e in all_target if dependency_trust(e, dataset) == TRUST_VERIFIED]
    as_source = [e for e in all_source if dependency_trust(e, dataset) == TRUST_VERIFIED]
    diag_target = [e for e in all_target if e not in as_target]
    diag_source = [e for e in all_source if e not in as_source]

    candidates = dataset.dependency_review_register.get("review_items", []) or []
    # Only counted for visibility in the Decision artifact; never executed.
    relevant_candidates = 0
    for c in candidates:
        rel = c.get("candidate_relationship", "")
        if requirement_id in rel:
            relevant_candidates += 1

    if edges:
        note = (
            f"{len(as_target) + len(as_source)} verified and "
            f"{len(diag_target) + len(diag_source)} diagnostic dependency edge(s) touch "
            "this requirement; trust is derived per edge via dependency_trust(). "
            "Review-register candidates were NOT executed."
        )

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
        diagnostic_edges_as_target=diag_target,
        diagnostic_edges_as_source=diag_source,
        unresolved_candidate_count=relevant_candidates,
        note=note,
    )
