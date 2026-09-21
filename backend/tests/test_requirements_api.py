def test_list_requirements_returns_exactly_the_four_engine_requirements(client):
    r = client.get("/api/v1/requirements")
    assert r.status_code == 200
    ids = sorted(req["requirement_id"] for req in r.json())
    assert ids == ["REQ-0001", "REQ-0002", "REQ-0003", "REQ-0004"]


def test_requirement_never_leaks_source_file_path(client):
    r = client.get("/api/v1/requirements/REQ-0001")
    assert r.status_code == 200
    body = r.json()
    assert "_source_file" not in body
    assert body["latest_rule_version_id"] == "RULE-0001-V1"
    assert body["latest_rule_version_status"] == "DRAFT"


def test_unknown_requirement_is_404(client):
    r = client.get("/api/v1/requirements/REQ-9999")
    assert r.status_code == 404
