"""
Local OCR (Tesseract) — thin wiring, deliberately separate from the frozen
AI module and from the existing LLM extraction pipeline.

Scope, precisely:
    uploaded image bytes -> Tesseract -> raw text -> returned to the caller

That's all. This module:
  * never calls Ollama or anything in app.modules.ai,
  * never writes to Project Facts or any Document record,
  * never assigns a confidence score (Tesseract doesn't give a meaningful
    one at this level — inventing one would be exactly the kind of
    fabricated confidence this project explicitly avoids),
  * is not a replacement for, or a second implementation of, the existing
    text -> LLM extraction -> human confirmation -> Project Facts flow
    (app/modules/ai/services/documents.py, routers/ai_documents.py) — it
    only produces the *input text* for that unchanged pipeline. A human
    still runs the existing extraction step and confirms fields themselves;
    OCR output is never auto-fed into Project Facts.

PDF is intentionally not supported in this pass: turning a PDF into
page images requires poppler (a system dependency beyond "Tesseract is
installed"), which is unverified on arbitrary hosts. Convert a PDF to an
image first, or paste text directly into the existing extraction panel.
"""
from __future__ import annotations

import io
import logging
import os

import pytesseract
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("iris.ai_integration.ocr")

_SUPPORTED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
    "image/tiff",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — generous for a single-page scan/photo


class OCRUnavailable(Exception):
    """Raised (and only raised) when the Tesseract binary itself cannot be
    reached — not installed, not on PATH, or IRIS_TESSERACT_CMD points
    somewhere invalid. Mirrors the same 503-shaped contract as Ollama
    unavailability elsewhere in this codebase."""


class OCRInvalidInput(Exception):
    """Raised for a caller-supplied problem: unsupported content type, file
    too large, or bytes that aren't a readable image. Maps to a 4xx, never
    a 500."""


def _configure_tesseract_cmd() -> None:
    """Optional explicit path to the tesseract binary (Windows installs are
    not always on PATH). Only applied if the env var is set — the default
    is to resolve `tesseract` via PATH, exactly like pytesseract does out
    of the box."""
    cmd = os.environ.get("IRIS_TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def is_available() -> bool:
    """Cheap reachability check, mirroring ai.core.health() for Ollama.
    Used by GET /api/v1/ai/status so the frontend can show OCR availability
    without attempting a real extraction first."""
    _configure_tesseract_cmd()
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _tesseract_version() -> str:
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return "unknown"


def extract_text_from_image(image_bytes: bytes, content_type: str | None) -> dict:
    """Run local Tesseract OCR over an uploaded image and return raw text.

    Returns {text, char_count, engine, warnings}. Deliberately dumb and
    honest: no LLM call, no invented confidence, no persistence. If
    Tesseract finds nothing, text is "" with a warning saying so rather
    than fabricating content.
    """
    if content_type and content_type.lower() not in _SUPPORTED_CONTENT_TYPES:
        raise OCRInvalidInput(
            f"Unsupported content type '{content_type}'. Supported: "
            f"{', '.join(sorted(_SUPPORTED_CONTENT_TYPES))}. "
            "PDF is not supported in this build — convert to an image first, "
            "or paste text directly into the extraction panel."
        )
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise OCRInvalidInput(
            f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)}MB limit."
        )
    if not image_bytes:
        raise OCRInvalidInput("Uploaded file is empty.")

    _configure_tesseract_cmd()

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except UnidentifiedImageError as exc:
        raise OCRInvalidInput("Could not read this file as an image.") from exc

    try:
        text = pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailable(
            "Tesseract OCR engine is not installed or not on PATH. "
            "Install it, or set IRIS_TESSERACT_CMD to its full executable path."
        ) from exc
    except Exception as exc:  # never let a raw Tesseract/subprocess error leak
        logger.exception("Tesseract OCR failed")
        raise OCRUnavailable(f"OCR engine error: {exc}") from exc

    warnings: list[str] = []
    if not text.strip():
        warnings.append(
            "No text was recognized in this image. Try a higher-resolution "
            "scan, or paste the text directly."
        )

    return {
        "text": text,
        "char_count": len(text),
        "engine": f"tesseract {_tesseract_version()}",
        "warnings": warnings,
    }
