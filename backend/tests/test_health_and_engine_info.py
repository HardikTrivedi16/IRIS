def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine_dataset_loaded"] is True
    assert body["requirement_count"] == 4
    assert body["persistence_backend"] == "memory"


def test_engine_info_reports_zero_active_rule_versions(client):
    """This is the single most important truth the API must never hide:
    every Rule Version in the supplied dataset is DRAFT."""
    r = client.get("/api/v1/engine")
    assert r.status_code == 200
    body = r.json()
    counts = body["counts"]["rule_versions_by_status"]
    assert counts.get("ACTIVE", 0) == 0
    assert counts.get("DRAFT") == 6
    assert len(body["known_conflicts"]) == 1
    assert body["known_conflicts"][0]["conflict_id"] == "OVERLAP-0001"
