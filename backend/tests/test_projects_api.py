def test_list_projects_returns_seeded_demo_projects(client):
    r = client.get("/api/v1/projects")
    ids = sorted(p["id"] for p in r.json())
    assert ids == ["freshbite", "mahapharm"]


def test_get_missing_project_is_404(client):
    r = client.get("/api/v1/projects/does-not-exist")
    assert r.status_code == 404


def test_create_project_then_fetch(client):
    r = client.post(
        "/api/v1/projects",
        json={"name": "Test Co", "industry": "food", "characteristics": {"wastewater": True}},
    )
    assert r.status_code == 201
    project = r.json()
    assert project["name"] == "Test Co"
    got = client.get(f"/api/v1/projects/{project['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == project["id"]


def test_set_and_get_project_facts(client):
    r = client.post(
        "/api/v1/projects/mahapharm/facts",
        json={"facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True}},
    )
    assert r.status_code == 200
    assert r.json()["facts"]["project.likely_to_discharge_sewage_or_trade_effluent"] is True

    got = client.get("/api/v1/projects/mahapharm/facts")
    assert got.json()["facts"]["project.likely_to_discharge_sewage_or_trade_effluent"] is True


def test_facts_for_missing_project_is_404(client):
    r = client.get("/api/v1/projects/does-not-exist/facts")
    assert r.status_code == 404


def test_evaluate_uses_stored_project_facts_when_none_supplied_in_request(client):
    client.post(
        "/api/v1/projects/mahapharm/facts",
        json={"facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True}},
    )
    r = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": "mahapharm",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "NON_PRODUCTION",
            "persist": False,
        },
    )
    assert r.json()["decision"]["final_state"] == "APPLICABLE"


def test_create_and_list_documents(client):
    r = client.post(
        "/api/v1/projects/mahapharm/documents",
        json={"name": "Chemical Inventory.pdf", "linked_requirement_ids": ["REQ-0001"]},
    )
    assert r.status_code == 201
    listing = client.get("/api/v1/projects/mahapharm/documents")
    names = [d["name"] for d in listing.json()]
    assert "Chemical Inventory.pdf" in names
