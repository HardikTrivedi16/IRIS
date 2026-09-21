"""
PDF → text, page by page (P2-M).

    PDF ──► PyMuPDF embedded-text extraction, per page
              │
              ├─ page has usable embedded text ──► use it (NO OCR)
              └─ page lacks usable text ─────────► render page ► Tesseract OCR

PyMuPDF is NOT OCR: it reads text that is already embedded in the PDF. Only
pages without usable embedded text (typically scanned pages) are rendered to
an image and OCR'd with the same local Tesseract the image path uses.

Like ``ocr_service``, this only produces editable INPUT TEXT for the existing,
unchanged extraction → human confirmation → consistency pipeline. It never
calls an LLM, never writes Project Facts or Document records, and never
assigns a confidence score. Page provenance is preserved: every page reports
how its text was obtained, and the returned text carries explicit page
markers so a reviewer can see which page a value came from.

Licensing note: PyMuPDF is AGPL-3.0 (or commercial). Review before any
production/government deployment.
"""
from __future__ import annotations

import io
import logging
import re

import pymupdf
import pytesseract
from PIL import Image

from .ocr_service import OCRInvalidInput, OCRUnavailable, _configure_tesseract_cmd, _tesseract_version

logger = logging.getLogger("iris.ai_integration.pdf")

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 30
#: A page needs at least this many letters/digits of embedded text to be
#: treated as text-native. Below it the page is rendered and OCR'd.
MIN_USABLE_CHARS = 25
OCR_DPI = 200

METHOD_EMBEDDED = "EMBEDDED_TEXT"
METHOD_OCR = "OCR"
METHOD_OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
METHOD_EMPTY = "NO_TEXT_FOUND"


def looks_like_pdf(data: bytes, content_type: str | None) -> bool:
    return (content_type or "").lower() == "application/pdf" or data[:5] == b"%PDF-"


def _usable_chars(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]", text or ""))


def extract_text_from_pdf(pdf_bytes: bytes) -> dict:
    if not pdf_bytes:
        raise OCRInvalidInput("Uploaded file is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise OCRInvalidInput(f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)}MB limit.")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise OCRInvalidInput("Could not read this file as a PDF (it may be corrupt).") from exc

    try:
        if doc.needs_pass:
            raise OCRInvalidInput("This PDF is password-protected; remove the password first.")
        if doc.page_count == 0:
            raise OCRInvalidInput("This PDF has no pages.")
        if doc.page_count > MAX_PDF_PAGES:
            # Reject rather than silently truncate: dropping pages would lose
            # evidence without the reviewer knowing.
            raise OCRInvalidInput(
                f"This PDF has {doc.page_count} pages; the limit is {MAX_PDF_PAGES}. "
                "Split it and upload the relevant pages."
            )

        _configure_tesseract_cmd()
        pages: list[dict] = []
        chunks: list[str] = []
        ocr_used = 0
        ocr_missing = False

        for index in range(doc.page_count):
            page = doc.load_page(index)
            n = index + 1
            embedded = page.get_text("text") or ""
            page_warnings: list[str] = []

            if _usable_chars(embedded) >= MIN_USABLE_CHARS:
                method, text = METHOD_EMBEDDED, embedded
            else:
                pix = page.get_pixmap(dpi=OCR_DPI)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    text = pytesseract.image_to_string(image)
                    method = METHOD_OCR
                    ocr_used += 1
                except pytesseract.TesseractNotFoundError:
                    ocr_missing = True
                    method, text = METHOD_OCR_UNAVAILABLE, embedded
                    page_warnings.append(
                        "This page has no usable embedded text and the Tesseract OCR "
                        "engine is not available, so its text could not be read."
                    )
                except Exception as exc:  # never leak raw subprocess errors
                    logger.exception("Tesseract failed on PDF page %s", n)
                    ocr_missing = True
                    method, text = METHOD_OCR_UNAVAILABLE, embedded
                    page_warnings.append(f"OCR failed on this page: {exc.__class__.__name__}.")
                if method == METHOD_OCR and not text.strip():
                    method = METHOD_EMPTY
                    page_warnings.append("No text was recognized on this page.")

            pages.append({
                "page": n,
                "method": method,
                "char_count": len(text),
                "warnings": page_warnings,
            })
            chunks.append(f"--- Page {n} ({method.replace('_', ' ').lower()}) ---\n{text.strip()}")
    finally:
        doc.close()

    if ocr_missing and all(p["method"] in (METHOD_OCR_UNAVAILABLE, METHOD_EMPTY) for p in pages):
        raise OCRUnavailable(
            "No page of this PDF has usable embedded text, and the Tesseract OCR engine "
            "is not available to read the scanned pages. Install Tesseract or set "
            "IRIS_TESSERACT_CMD."
        )

    warnings: list[str] = []
    for p in pages:
        warnings.extend(f"Page {p['page']}: {w}" for w in p["warnings"])
    text = "\n\n".join(chunks)
    engine = f"pymupdf {pymupdf.VersionBind} (embedded text)"
    if ocr_used:
        engine += f" + tesseract {_tesseract_version()} (OCR on {ocr_used} page{'s' if ocr_used != 1 else ''})"

    return {
        "text": text,
        "char_count": len(text),
        "engine": engine,
        "warnings": warnings,
        "source_format": "pdf",
        "page_count": len(pages),
        "pages": pages,
    }
