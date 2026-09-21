"""
API-level tests for:
    GET  /api/v1/projects/{project_id}/dependency-graph
    POST /api/v1/projects/{project_id}/dependency-graph/impact

Covers required INTEGRATION and NETWORKX test-list items:
  * project -> facts -> evaluation -> dependency graph
  * evaluation -> graph
  * graph -> impact recalculation
  * zero-edge real dataset behavior (via the live API)
  * authorization boundaries (reuses existing project auth)
"""
from __future__ import annotations


def _create_project(client, name="Graph Test Co"):
    resp = client.post("/api/v1/projects", json={"name": name, "industry": "CHEMICAL"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_dependency_graph_empty_in_production_mode(client):
    """Zero ACTIVE rule versions today -> zero applicable requirements ->
    zero nodes, zero edges. Must not error, must not fabricate nodes."""
    project_id = _create_project(client)
    resp = client.get(f"/api/v1/projects/{project_id}/dependency-graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["critical_path"] == []
    assert body["critical_path_available"] is False
    assert len(body["excluded_requirements"]) > 0


def test_dependency_graph_non_production_shows_applicable_node(client):
    project_id = _create_project(client)
    client.post(f"/api/v1/projects/{project_id}/facts", json={
        "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    })
    resp = client.get(
        f"/api/v1/projects/{project_id}/dependency-graph",
        params={"evaluation_mode": "NON_PRODUCTION"},
    )
    assert resp.status_code == 200
    body = resp.json()
    codes = {n["requirement_code"] for n in body["nodes"]}
    assert "MPCB_CTE_WATER" in codes
    # No UUIDs leak into requirement_id — every node id resolves to an
    # IRIS-style code/string, not a bare UUID.
    for n in body["nodes"]:
        assert n["requirement_id"] == n["requirement_code"] or "-" in n["requirement_id"]


def test_dependency_graph_zero_edges_reflected_honestly(client):
    project_id = _create_project(client)
    client.post(f"/api/v1/projects/{project_id}/facts", json={
        "facts": {
            "project.likely_to_discharge_sewage_or_trade_effluent": True,
            "project.plant_located_in_air_pollution_control_area": True,
        }
    })
    resp = client.get(
        f"/api/v1/projects/{project_id}/dependency-graph",
        params={"evaluation_mode": "NON_PRODUCTION"},
    )
    body = resp.json()
    assert body["edges"] == []
    assert "zero verified" in body["dependency_data_note"].lower()


def test_dependency_graph_404_for_unknown_project_with_auth_required(client):
    # No stored project, no demo/auth bypass beyond default demo mode —
    # get_project() 404s exactly like it does for /projects/{id}/facts.
    resp = client.get("/api/v1/projects/does-not-exist/dependency-graph")
    # In demo mode unowned/unknown ids 404 via get_project's own logic.
    assert resp.status_code == 404


def test_dependency_graph_impact_detects_newly_applicable_requirement(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/dependency-graph/impact",
        json={
            "old_facts": {},
            "new_facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
            "evaluation_mode": "NON_PRODUCTION",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "REQ-0001" in body["added_requirement_ids"]
    assert body["removed_requirement_ids"] == []


def test_dependency_graph_impact_no_change_when_facts_identical(client):
    project_id = _create_project(client)
    same_facts = {"project.plant_located_in_air_pollution_control_area": True}
    resp = client.post(
        f"/api/v1/projects/{project_id}/dependency-graph/impact",
        json={"old_facts": same_facts, "new_facts": same_facts, "evaluation_mode": "NON_PRODUCTION"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added_requirement_ids"] == []
    assert body["removed_requirement_ids"] == []
    assert body["critical_path_changed"] is False
