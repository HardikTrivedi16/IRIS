"""
Tests for local Tesseract OCR:

    POST /api/v1/projects/{project_id}/documents/ocr

These run against the REAL Tesseract binary (no mocking) — this endpoint's
entire job is being a thin wrapper around it, so the meaningful test is
"does it actually call Tesseract and behave correctly", not "does a fake
provider get invoked". If Tesseract isn't installed in a given CI
environment, the whole module is skipped rather than failing noisily.

Covers:
  * real image -> real extracted text, never touching Project Facts
  * unsupported content type (PDF) -> 422, not a crash
  * corrupt/unreadable image bytes -> 422
  * missing/unauthorized project -> 404 (same get_project as every other endpoint)
  * GET /api/v1/ai/status reports ocr_available independently of Ollama
"""
from __future__ import annotations

import io

import pytest

from app.ai_integration import ocr_service

pytestmark = pytest.mark.skipif(
    not ocr_service.is_available(),
    reason="Tesseract binary not installed/reachable in this environment",
)


def _create_project(client, name="OCR Test Co"):
    resp = client.post("/api/v1/projects", json={"name": name, "industry": "FOOD"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _sample_image_bytes() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (500, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), "IRIS OCR TEST DOCUMENT", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_extracts_real_text_and_never_touches_facts(client):
    project_id = _create_project(client)
    before = client.get(f"/api/v1/projects/{project_id}/facts").json()["facts"]
    assert before == {}

    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/ocr",
        files={"file": ("scan.png", _sample_image_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "IRIS" in body["text"].upper()
    assert body["char_count"] > 0
    assert body["engine"].startswith("tesseract")
    assert isinstance(body["warnings"], list)

    after = client.get(f"/api/v1/projects/{project_id}/facts").json()["facts"]
    assert after == {}, "OCR must never auto-persist Project Facts"


def test_ocr_rejects_pdf_with_clean_422_not_a_crash(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/ocr",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 422
    assert "pdf" in resp.json()["detail"].lower()


def test_ocr_rejects_corrupt_image_bytes(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/ocr",
        files={"file": ("bad.png", b"this is not an image", "image/png")},
    )
    assert resp.status_code == 422


def test_ocr_requires_project_authorization(client):
    resp = client.post(
        "/api/v1/projects/does-not-exist/documents/ocr",
        files={"file": ("scan.png", _sample_image_bytes(), "image/png")},
    )
    assert resp.status_code == 404


def test_ocr_empty_file_is_rejected(client):
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/ocr",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 422


def test_ai_status_reports_ocr_availability_independent_of_ollama(client):
    resp = client.get("/api/v1/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "ocr_available" in body
    assert body["ocr_available"] is True  # Tesseract is installed per the module skip guard


def test_ocr_unavailable_returns_503_not_500(client, monkeypatch):
    """Simulates Tesseract genuinely being unreachable (uninstalled/misconfigured)
    without requiring an environment where it's actually missing."""
    import app.routers.ocr as ocr_router

    def _boom(image_bytes, content_type):
        raise ocr_service.OCRUnavailable("Tesseract OCR engine is not installed or not on PATH.")

    monkeypatch.setattr(ocr_router, "extract_text_from_image", _boom)

    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/ocr",
        files={"file": ("scan.png", _sample_image_bytes(), "image/png")},
    )
    assert resp.status_code == 503
