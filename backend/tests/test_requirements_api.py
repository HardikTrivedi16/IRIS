def test_list_requirements_returns_exactly_the_dataset_requirements(client):
    from app import engine_service

    r = client.get("/api/v1/requirements")
    assert r.status_code == 200
    ids = sorted(req["requirement_id"] for req in r.json())
    # Compare against the live dataset rather than a hardcoded 4-item
    # list, which had already gone stale (Shared+Food/Pharma tranches
    # added 11 more Requirements) without this test catching it.
    assert ids == sorted(engine_service.get_dataset().requirements.keys())


def test_requirement_never_leaks_source_file_path(client):
    r = client.get("/api/v1/requirements/REQ-0001")
    assert r.status_code == 200
    body = r.json()
    assert "_source_file" not in body
    assert body["latest_rule_version_id"] == "RULE-0001-V2"
    assert body["latest_rule_version_status"] == "DRAFT"


def test_unknown_requirement_is_404(client):
    r = client.get("/api/v1/requirements/REQ-9999")
    assert r.status_code == 404
