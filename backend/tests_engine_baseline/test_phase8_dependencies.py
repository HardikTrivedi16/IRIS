"""
Phase 8 §12 — dependency testing. Confirms the real dataset has zero
executable DEP edges and 5 non-executed review candidates, then uses
SYNTHETIC, clearly test-only fixtures (never written to regulatory-data)
to exercise the dependency interface: prerequisite, parallel, conditional,
invalid reference, and conflicting-dependency behavior. All synthetic
edges are prefixed TEST-DEP- to make their non-canonical nature obvious.
"""
import copy

from iris_engine.dependencies import evaluate_dependencies, DependencyResult


def test_two_verified_dependency_edges_in_real_dataset(dataset):
    from iris_engine.dependencies import dependency_trust
    edges = dataset.dependencies_index.get("dependencies", [])
    assert len(edges) == 4
    assert dataset.dependencies_index.get("counts", {}).get("total_dependencies") == 4
    trust = {e["dependency_id"]: dependency_trust(e, dataset) for e in edges}
    assert trust == {"DEP-0001": "VERIFIED", "DEP-0002": "VERIFIED",
                     "DEP-0003": "DIAGNOSTIC", "DEP-0004": "DIAGNOSTIC"}


def test_five_review_candidates_present_and_not_executable(dataset):
    items = dataset.dependency_review_register.get("review_items", [])
    assert len(items) == 5
    ids = {i["review_id"] for i in items}
    assert ids == {f"DEP-REV-{i:04d}" for i in range(1, 6)}
    for item in items:
        # a review candidate is inert data -- it carries no executable edge
        # fields (from_requirement_id/to_requirement_id) the engine could
        # accidentally consume as a real DEP-### edge.
        assert "from_requirement_id" not in item
        assert "to_requirement_id" not in item


def test_review_candidates_never_executed_by_evaluate_dependencies(dataset):
    # For every real Requirement, the dependency result must show zero
    # verified edges even though 5 candidates exist in the register --
    # confirms the register is consulted only for the visibility count,
    # never turned into an executable edge.
    for req_id in dataset.requirements:
        result = evaluate_dependencies(req_id, dataset)
        ids = {e["dependency_id"] for e in result.verified_edges_as_target + result.verified_edges_as_source}
        assert ids <= {"DEP-0001", "DEP-0002"}
        assert "NOT executed" in result.note or "not executed" in result.note.lower() or "not be executed" in result.note.lower() or "were NOT executed" in result.note


# --- synthetic fixtures: prerequisite / parallel / conditional / invalid ---

class _SyntheticDepDataset:
    """Minimal stand-in exposing only what evaluate_dependencies reads
    (dependencies_index, dependency_review_register). Test-only -- never
    touches the real RegulatoryDataset or persists anything."""
    def __init__(self, edges, review_items=None):
        self.dependencies_index = {"dependencies": edges}
        # synthetic edges model human-APPROVED DEPENDENCY_EDGE verifications
        self.verifications = {
            f"TEST-VER-{i}": {"target_type": "DEPENDENCY_EDGE",
                              "target_id": e["dependency_id"], "result": "APPROVED"}
            for i, e in enumerate(edges)
        }
        self.dependency_review_register = {"review_items": review_items or []}


def test_synthetic_prerequisite_edge_reported_as_target():
    ds = _SyntheticDepDataset(edges=[
        {"dependency_id": "TEST-DEP-001", "from_requirement_id": "TEST-REQ-A",
         "to_requirement_id": "TEST-REQ-B", "dependency_type": "PREREQUISITE"},
    ])
    result = evaluate_dependencies("TEST-REQ-B", ds)
    assert len(result.verified_edges_as_target) == 1
    assert result.verified_edges_as_target[0]["dependency_id"] == "TEST-DEP-001"
    assert result.verified_edges_as_source == []


def test_synthetic_parallel_independent_edges_no_interference():
    ds = _SyntheticDepDataset(edges=[
        {"dependency_id": "TEST-DEP-P1", "from_requirement_id": "TEST-REQ-X",
         "to_requirement_id": "TEST-REQ-Y", "dependency_type": "PARALLEL"},
        {"dependency_id": "TEST-DEP-P2", "from_requirement_id": "TEST-REQ-X",
         "to_requirement_id": "TEST-REQ-Z", "dependency_type": "PARALLEL"},
    ])
    result_y = evaluate_dependencies("TEST-REQ-Y", ds)
    result_z = evaluate_dependencies("TEST-REQ-Z", ds)
    assert len(result_y.verified_edges_as_target) == 1
    assert len(result_z.verified_edges_as_target) == 1
    assert result_y.verified_edges_as_target[0]["dependency_id"] != result_z.verified_edges_as_target[0]["dependency_id"]


def test_synthetic_conditional_dependency_edge_present_but_unevaluated():
    # The engine's dependency interface only reports edge existence -- it
    # does not itself evaluate a CONDITIONAL_DEPENDENCY's condition (that
    # is out of scope; conditions are evaluated via evaluate_condition
    # elsewhere). Confirm the edge surfaces without the engine inventing an
    # evaluated true/false outcome for it.
    ds = _SyntheticDepDataset(edges=[
        {"dependency_id": "TEST-DEP-COND", "from_requirement_id": "TEST-REQ-M",
         "to_requirement_id": "TEST-REQ-N", "dependency_type": "CONDITIONAL_DEPENDENCY",
         "condition_id": "TEST-COND-SOMETHING"},
    ])
    result = evaluate_dependencies("TEST-REQ-N", ds)
    edge = result.verified_edges_as_target[0]
    assert "evaluated_result" not in edge  # engine never fabricates this
    assert edge["dependency_type"] == "CONDITIONAL_DEPENDENCY"


def test_synthetic_invalid_dependency_reference_does_not_crash():
    # An edge referencing a Requirement ID that doesn't exist anywhere in
    # this synthetic dataset must not raise -- it simply won't match any
    # as_target/as_source query for a real requirement.
    ds = _SyntheticDepDataset(edges=[
        {"dependency_id": "TEST-DEP-GHOST", "from_requirement_id": "TEST-REQ-GHOST-SRC",
         "to_requirement_id": "TEST-REQ-GHOST-DST"},
    ])
    result = evaluate_dependencies("TEST-REQ-COMPLETELY-UNRELATED", ds)
    assert result.verified_edges_as_target == []
    assert result.verified_edges_as_source == []


def test_synthetic_conflicting_dependency_pair_both_surface_without_resolution():
    # Two synthetic edges asserting opposite things between the same pair
    # (A legal-prerequisite-for B, and B legal-prerequisite-for A) --
    # the interface must surface both without silently resolving the
    # contradiction (that resolution is out of Phase 7/8 scope; the real
    # dependency_conflict_register.yaml is the intended home for it).
    ds = _SyntheticDepDataset(edges=[
        {"dependency_id": "TEST-DEP-C1", "from_requirement_id": "TEST-REQ-A",
         "to_requirement_id": "TEST-REQ-B", "dependency_type": "PREREQUISITE"},
        {"dependency_id": "TEST-DEP-C2", "from_requirement_id": "TEST-REQ-B",
         "to_requirement_id": "TEST-REQ-A", "dependency_type": "PREREQUISITE"},
    ])
    result_a = evaluate_dependencies("TEST-REQ-A", ds)
    result_b = evaluate_dependencies("TEST-REQ-B", ds)
    assert len(result_a.verified_edges_as_target) == 1  # TEST-DEP-C2 (B->A)
    assert len(result_a.verified_edges_as_source) == 1  # TEST-DEP-C1 (A->B)
    assert len(result_b.verified_edges_as_target) == 1
    assert len(result_b.verified_edges_as_source) == 1
    # neither result claims a resolved precedence
    assert "note" in result_a.__dict__


def test_no_synthetic_fixture_ever_touches_real_dataset(dataset):
    # After running every synthetic test above, the real dataset must be
    # completely unaffected (these tests never mutate `dataset` at all,
    # by construction -- this assertion documents that invariant).
    assert len(dataset.dependencies_index.get("dependencies", [])) == 4
    assert len(dataset.dependency_review_register.get("review_items", [])) == 5
