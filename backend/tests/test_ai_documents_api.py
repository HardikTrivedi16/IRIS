"""
API-level tests for:
    GET  /api/v1/ai/status
    POST /api/v1/projects/{project_id}/documents/extract
    POST /api/v1/projects/{project_id}/documents/classify

No live Ollama daemon is running in CI, so these deliberately test the
SAFE-DEGRADATION path (503, not a crash) through the real HTTP stack —
this is the "Ollama unavailable" required test, run for real rather than
mocked at the unit level.
"""
from __future__ import annotations


def _create_project(client, name="AI Test Co"):
    resp = client.post("/api/v1/projects", json={"name": name, "industry": "CHEMICAL"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_ai_status_reports_unreachable_without_live_ollama(client):
    resp = client.get("/api/v1/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_enabled"] is True
    assert body["ollama_reachable"] is False  # no daemon running in this environment
    assert "generation_model" in body


def test_extract_document_degrades_safely_without_live_ollama(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/extract",
        json={"text": "Some registration certificate text for Acme Chemicals."},
    )
    # No live Ollama -> clean 503, not a 500 crash and not a fabricated result.
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


def test_classify_document_degrades_safely_without_live_ollama(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/classify",
        json={"text": "Some document text."},
    )
    assert resp.status_code == 503


def test_extract_document_requires_project_authorization(client):
    resp = client.post(
        "/api/v1/projects/does-not-exist/documents/extract",
        json={"text": "text"},
    )
    assert resp.status_code == 404


def test_extract_document_rejects_empty_text(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/extract",
        json={"text": ""},
    )
    assert resp.status_code == 422  # pydantic min_length=1 on DocumentExtractIn
