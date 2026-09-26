"""Dependency Tranche 1: four authored edges, derived trust, executable vs informational."""
import uuid

from dependency_engine import ApplicableRequirement, DependencyEdge, DependencyService, RelationshipType
from iris_engine.dependencies import dependency_trust, evaluate_dependencies

EXPECTED = {
    "DEP-0001": ("REQ-0006", "REQ-0007", "PREREQUISITE"),
    "DEP-0002": ("REQ-0003", "REQ-0015", "PREREQUISITE"),
    "DEP-0003": ("REQ-0001", "REQ-0010", "REQUIRES_OUTCOME_OF"),
    "DEP-0004": ("REQ-0002", "REQ-0010", "REQUIRES_OUTCOME_OF"),
}


def _edges(dataset):
    return {e["dependency_id"]: e for e in dataset.dependencies_index["dependencies"]}


def test_four_records_load_and_endpoints_resolve(dataset):
    edges = _edges(dataset)
    assert set(edges) == set(EXPECTED)
    counts = dataset.dependencies_index["counts"]
    assert counts["total_dependencies"] == 4
    assert counts["by_type"] == {"PREREQUISITE": 2, "REQUIRES_OUTCOME_OF": 2}
    for did, (a, b, t) in EXPECTED.items():
        e = edges[did]
        assert (e["from_requirement_id"], e["to_requirement_id"], e["dependency_type"]) == (a, b, t)
        assert a in dataset.requirements and b in dataset.requirements
        assert all(i in dataset.evidence for i in e["evidence_ids"])
        assert all(i in dataset.sources for i in e["source_ids"])
        assert "trust" not in e  # trust is derived, never persisted


def test_two_prerequisite_edges_have_approved_edge_ver_and_are_verified(dataset):
    edges = _edges(dataset)
    for dep, ver_id in (("DEP-0001", "VER-0018"), ("DEP-0002", "VER-0019")):
        v = dataset.verifications[ver_id]
        assert (v["target_type"], v["target_id"], v["result"]) == ("DEPENDENCY_EDGE", dep, "APPROVED")
        assert v["reviewer"] == "Hardik Trivedi"
        assert dependency_trust(edges[dep], dataset) == "VERIFIED"
        assert edges[dep]["verification_status"] == "VERIFIED"
    for dep in ("DEP-0003", "DEP-0004"):
        assert dependency_trust(edges[dep], dataset) == "DIAGNOSTIC"
        assert edges[dep]["verification_status"] == "UNVERIFIED"
        assert not [v for v in dataset.verifications.values() if v.get("target_id") == dep]


def test_removing_an_edge_ver_unverifies_that_edge(dataset):
    import copy
    edges = _edges(dataset)
    for ver_id, dep, other in (("VER-0018", "DEP-0001", "DEP-0002"), ("VER-0019", "DEP-0002", "DEP-0001")):
        ds = copy.copy(dataset)
        ds.verifications = {k: v for k, v in dataset.verifications.items() if k != ver_id}
        assert dependency_trust(edges[dep], ds) == "DIAGNOSTIC"
        assert dependency_trust(edges[other], ds) == "VERIFIED"


def test_verification_index_counts_consistent(dataset):
    import yaml, pathlib
    idx = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1] / "regulatory-data/index/verifications_index.yaml").read_text(encoding="utf-8"))
    assert idx["counts"]["total_verifications"] == len(idx["verifications"]) == len(dataset.verifications) == 19


def test_trust_derivation_rules(dataset):
    edges = _edges(dataset)

    class DS:
        pass

    def with_ver(dep_id, result="APPROVED", ttype="DEPENDENCY_EDGE"):
        ds = DS()
        ds.verifications = {"VER-T": {"target_type": ttype, "target_id": dep_id, "result": result}}
        return ds

    assert dependency_trust(edges["DEP-0001"], with_ver("DEP-0001")) == "VERIFIED"
    assert dependency_trust(edges["DEP-0001"], with_ver("DEP-0001", "REJECTED")) == "DIAGNOSTIC"
    assert dependency_trust(edges["DEP-0001"], with_ver("DEP-0001", ttype="RULE_VERSION")) == "DIAGNOSTIC"
    assert dependency_trust(edges["DEP-0001"], with_ver("DEP-0002")) == "DIAGNOSTIC"
    # informational edges can never be VERIFIED, even with an APPROVED VER
    assert dependency_trust(edges["DEP-0003"], with_ver("DEP-0003")) == "DIAGNOSTIC"


def test_diagnostic_edges_reported_for_hazwaste(dataset):
    r = evaluate_dependencies("REQ-0010", dataset)
    assert {e["dependency_id"] for e in r.diagnostic_edges_as_target} == {"DEP-0003", "DEP-0004"}
    assert r.verified_edges_as_target == []


def test_verified_edges_reported_for_boiler_and_drugs(dataset):
    assert [e["dependency_id"] for e in evaluate_dependencies("REQ-0007", dataset).verified_edges_as_target] == ["DEP-0001"]
    assert [e["dependency_id"] for e in evaluate_dependencies("REQ-0015", dataset).verified_edges_as_target] == ["DEP-0002"]


def test_adapter_admits_exactly_two_executable_edges_and_reports_diagnostics(dataset):
    from app.graph.adapter import build_graph_inputs
    decisions = [{"requirement_id": r, "final_state": "APPLICABLE"} for r in dataset.requirements]
    res = build_graph_inputs("P", decisions, dataset)
    assert len(res.dependencies) == 2
    assert all(e.relationship_type == RelationshipType.PREREQUISITE for e in res.dependencies)
    assert {d["dependency_id"] for d in res.diagnostic_relationships} == {"DEP-0003", "DEP-0004"}
    assert all(d["executable"] is False for d in res.diagnostic_relationships)


def test_prerequisite_executable_informational_excluded():
    def req(code):
        return ApplicableRequirement(uuid.uuid4(), code, code, uuid.uuid4())

    a, b, c = req("A"), req("B"), req("C")
    edges = [
        DependencyEdge(a.requirement_id, b.requirement_id, RelationshipType.PREREQUISITE),
        DependencyEdge(c.requirement_id, b.requirement_id, RelationshipType.REQUIRES_OUTCOME_OF),
    ]
    states = {r.requirement_id: False for r in (a, b, c)}
    analysis = DependencyService().analyze([a, b, c], edges, states)
    assert {e.relationship_type for e in analysis.edges} == {RelationshipType.PREREQUISITE}
    assert any(i.reason == "NON_EXECUTABLE_RELATIONSHIP_TYPE" for i in analysis.ignored_dependencies)
    node_b = next(n for n in analysis.nodes if n.requirement_code == "B")
    assert tuple(node_b.direct_prerequisite_ids) == (a.requirement_id,)


def test_rejected_pairs_have_no_edge(dataset):
    pairs = {(e["from_requirement_id"], e["to_requirement_id"]) for e in dataset.dependencies_index["dependencies"]}
    rejected = {
        ("REQ-0018", "REQ-0019"), ("REQ-0019", "REQ-0018"), ("REQ-0016", "REQ-0017"),
        ("REQ-0005", "REQ-0006"), ("REQ-0014", "REQ-0001"), ("REQ-0014", "REQ-0002"),
        ("REQ-0020", "REQ-0021"), ("REQ-0001", "REQ-0002"), ("REQ-0002", "REQ-0001"),
    }
    assert not (pairs & rejected)


def test_fssai_tiers_have_no_dependency_edges(dataset):
    fssai = {"REQ-0004", "REQ-0011", "REQ-0012", "REQ-0013"}
    for e in dataset.dependencies_index["dependencies"]:
        assert e["from_requirement_id"] not in fssai and e["to_requirement_id"] not in fssai


def test_relationships_expose_all_four_edges_independent_of_applicability(dataset):
    from app.graph.adapter import build_graph_inputs
    decisions = [{"requirement_id": r, "final_state": "REQUIRES_INFORMATION"} for r in dataset.requirements]
    res = build_graph_inputs("P", decisions, dataset)
    assert res.dependencies == ()  # nothing applicable -> nothing executable
    rel = {r["dependency_id"]: r for r in res.relationships}
    assert set(rel) == {"DEP-0001", "DEP-0002", "DEP-0003", "DEP-0004"}
    assert rel["DEP-0001"]["trust"] == "VERIFIED" and rel["DEP-0001"]["verification_ids"] == ["VER-0018"]
    assert rel["DEP-0002"]["executable"] is True
    assert rel["DEP-0003"]["trust"] == "DIAGNOSTIC" and rel["DEP-0003"]["executable"] is False
    assert rel["DEP-0004"]["verification_ids"] == []
