"""
P2-M — PDF text extraction with page-level OCR fallback.

PDFs are generated in-test with PyMuPDF: a text-native page carries an
embedded text layer; a "scanned" page is a rendered image of text with NO
text layer — so the only way to read it is OCR.
"""
import pymupdf
import pytest

from app.ai_integration import ocr_service, pdf_service
from app.ai_integration.ocr_service import OCRInvalidInput, OCRUnavailable
from app.ai_integration.pdf_service import (
    METHOD_EMBEDDED,
    METHOD_OCR,
    METHOD_OCR_UNAVAILABLE,
    extract_text_from_pdf,
)

TEXT_LINE = "Legal Name: SwaadHarvest Foods Private Limited"
SCAN_LINE = "Batch Number BATCH MP 002"

needs_tesseract = pytest.mark.skipif(not ocr_service.is_available(), reason="Tesseract not installed")


def _text_page(doc, line=TEXT_LINE):
    page = doc.new_page()
    page.insert_text((72, 100), line, fontsize=14)
    page.insert_text((72, 130), "SYNTHETIC TEST DOCUMENT — not a government record", fontsize=11)


def _scanned_page(doc, line=SCAN_LINE):
    """An image-only page: render text, then embed the picture with no text layer."""
    src = pymupdf.open()
    p = src.new_page()
    p.insert_text((72, 120), line, fontsize=28)
    png = p.get_pixmap(dpi=200).tobytes("png")
    src.close()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png)


def _pdf(*builders) -> bytes:
    doc = pymupdf.open()
    for b in builders:
        b(doc)
    data = doc.tobytes()
    doc.close()
    return data


def test_text_pdf_uses_embedded_text_and_never_ocr(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("text-native pages must not be OCR'd")

    monkeypatch.setattr(pdf_service.pytesseract, "image_to_string", boom)
    out = extract_text_from_pdf(_pdf(_text_page))
    assert out["page_count"] == 1
    assert out["pages"][0]["method"] == METHOD_EMBEDDED
    assert TEXT_LINE in out["text"]
    assert "--- Page 1" in out["text"]  # page provenance marker
    assert "tesseract" not in out["engine"]


@needs_tesseract
def test_scanned_pdf_is_ocrd():
    out = extract_text_from_pdf(_pdf(_scanned_page))
    [page] = out["pages"]
    assert page["method"] == METHOD_OCR
    assert "BATCH" in out["text"].upper()
    assert "tesseract" in out["engine"] and "OCR on 1 page" in out["engine"]


@needs_tesseract
def test_mixed_pdf_ocrs_only_the_scanned_page(monkeypatch):
    calls = []
    real = pdf_service.pytesseract.image_to_string

    def counting(img, *a, **k):
        calls.append(1)
        return real(img, *a, **k)

    monkeypatch.setattr(pdf_service.pytesseract, "image_to_string", counting)
    out = extract_text_from_pdf(_pdf(_text_page, _scanned_page, _text_page))
    assert [p["method"] for p in out["pages"]] == [METHOD_EMBEDDED, METHOD_OCR, METHOD_EMBEDDED]
    assert len(calls) == 1
    assert "--- Page 2 (ocr) ---" in out["text"]


def test_corrupt_pdf_rejected():
    with pytest.raises(OCRInvalidInput):
        extract_text_from_pdf(b"%PDF-1.4 this is not really a pdf")


def test_empty_rejected():
    with pytest.raises(OCRInvalidInput):
        extract_text_from_pdf(b"")


def test_oversized_bytes_rejected(monkeypatch):
    monkeypatch.setattr(pdf_service, "MAX_PDF_BYTES", 100)
    with pytest.raises(OCRInvalidInput, match="limit"):
        extract_text_from_pdf(_pdf(_text_page))


def test_too_many_pages_rejected_not_truncated(monkeypatch):
    monkeypatch.setattr(pdf_service, "MAX_PDF_PAGES", 2)
    with pytest.raises(OCRInvalidInput, match="limit is 2"):
        extract_text_from_pdf(_pdf(_text_page, _text_page, _text_page))


def test_encrypted_pdf_rejected():
    doc = pymupdf.open()
    _text_page(doc)
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()
    with pytest.raises(OCRInvalidInput, match="password"):
        extract_text_from_pdf(data)


def _no_tesseract(monkeypatch):
    def missing(*a, **k):
        raise pdf_service.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pdf_service.pytesseract, "image_to_string", missing)


def test_tesseract_unavailable_scanned_only_is_503(monkeypatch):
    _no_tesseract(monkeypatch)
    with pytest.raises(OCRUnavailable):
        extract_text_from_pdf(_pdf(_scanned_page))


def test_tesseract_unavailable_mixed_degrades_per_page(monkeypatch):
    _no_tesseract(monkeypatch)
    out = extract_text_from_pdf(_pdf(_text_page, _scanned_page))
    assert [p["method"] for p in out["pages"]] == [METHOD_EMBEDDED, METHOD_OCR_UNAVAILABLE]
    assert TEXT_LINE in out["text"]
    assert any(w.startswith("Page 2:") for w in out["warnings"])


# --- API ---------------------------------------------------------------------------

def test_api_accepts_pdf_and_persists_nothing(client):
    before = client.get("/api/v1/projects/freshbite/facts").json()
    r = client.post("/api/v1/projects/freshbite/documents/ocr",
                    files={"file": ("gst.pdf", _pdf(_text_page), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_format"] == "pdf" and body["pages"][0]["method"] == METHOD_EMBEDDED
    assert TEXT_LINE in body["text"]
    assert client.get("/api/v1/projects/freshbite/facts").json() == before
    assert client.get("/api/v1/projects/freshbite/documents").json() == []


def test_api_detects_pdf_by_magic_bytes(client):
    r = client.post("/api/v1/projects/freshbite/documents/ocr",
                    files={"file": ("upload.bin", _pdf(_text_page), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["source_format"] == "pdf"


def test_api_scanned_only_without_tesseract_is_503(client, monkeypatch):
    _no_tesseract(monkeypatch)
    r = client.post("/api/v1/projects/freshbite/documents/ocr",
                    files={"file": ("scan.pdf", _pdf(_scanned_page), "application/pdf")})
    assert r.status_code == 503
