"""
OCR Engine — wraps PaddleOCR + PyMuPDF for text extraction.

This module is the *only* place that interacts with PaddleOCR and
PyMuPDF.  The rest of the application calls ``run_ocr()`` and gets
back plain text + individual OCR line strings.

The PaddleOCR model is initialised lazily (on first call) so the
import of this module is fast and side-effect-free.
"""

from __future__ import annotations

import io
from typing import Tuple

import fitz  # PyMuPDF
import numpy as np
from paddleocr import PaddleOCR
from PIL import Image

# ---------------------------------------------------------------------------
# Lazy singleton — created on first use so ``import`` stays cheap.
# ---------------------------------------------------------------------------
_ocr_model: PaddleOCR | None = None


def _get_model() -> PaddleOCR:
    """Return (and lazily create) the global PaddleOCR instance."""
    global _ocr_model
    if _ocr_model is None:
        _ocr_model = PaddleOCR(
            use_textline_orientation=True,
            lang="en",
            enable_mkldnn=False,
            ocr_version="PP-OCRv4",
        )
    return _ocr_model


# ---------------------------------------------------------------------------
# Internal helpers (migrated from the original main.py)
# ---------------------------------------------------------------------------

def _normalize_ocr_result(ocr_results) -> list[str]:
    """Parse PaddleOCR 3.x predict() results into a flat list of strings.

    Supports both the 3.x dict-like API and legacy 2.x nested-list format.
    Returns a **list** of individual text lines (not a joined string) so
    downstream services can do line-level analysis.
    """
    if not ocr_results:
        return []

    texts: list[str] = []

    try:
        for page_result in ocr_results:
            if not page_result:
                continue

            # --- PaddleOCR 3.x dict-like result ---
            if hasattr(page_result, "rec_texts") or (
                isinstance(page_result, dict) and "rec_texts" in page_result
            ):
                rec_texts = (
                    page_result.get("rec_texts", [])
                    if isinstance(page_result, dict)
                    else getattr(page_result, "rec_texts", [])
                )
                for t in rec_texts:
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
                continue

            # --- Legacy PaddleOCR 2.x nested list ---
            if isinstance(page_result, (list, tuple)):
                for line in page_result:
                    if isinstance(line, dict):
                        text = line.get("text")
                        if text:
                            texts.append(text.strip())
                    elif isinstance(line, (list, tuple)) and len(line) > 1:
                        text_data = line[1]
                        if isinstance(text_data, (list, tuple)) and len(text_data) > 0:
                            text = text_data[0]
                            if isinstance(text, str) and text.strip():
                                texts.append(text.strip())

    except Exception:
        return []

    return texts


def _ocr_image_bytes(image_bytes: bytes) -> list[str]:
    """Run OCR on raw image bytes.  Returns a list of recognised lines."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    model = _get_model()
    ocr_results = model.predict(np.array(image))
    return _normalize_ocr_result(ocr_results)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ocr(file_bytes: bytes, filename: str = "") -> Tuple[str, list[str]]:
    """Run OCR on a file (PDF or image) and return extracted text.

    Parameters
    ----------
    file_bytes : bytes
        Raw file content.
    filename : str
        Original filename (used to detect PDF vs image).

    Returns
    -------
    (raw_text, ocr_lines)
        raw_text  : all text joined with newlines
        ocr_lines : individual OCR-recognised line strings
    """
    filename_lower = filename.lower()

    # --- PDF handling ---
    if file_bytes.startswith(b"%PDF-") or filename_lower.endswith(".pdf"):
        return _extract_pdf(file_bytes)

    # --- Image handling ---
    return _extract_image(file_bytes)


def _extract_pdf(file_bytes: bytes) -> Tuple[str, list[str]]:
    """Extract text from a PDF.  Uses embedded text first, falls back to OCR."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    all_lines: list[str] = []

    try:
        for page in doc:
            # Try embedded text first
            embedded_text = page.get_text().strip()

            if embedded_text:
                # Split into lines so downstream parsers work line-by-line
                for line in embedded_text.splitlines():
                    stripped = line.strip()
                    if stripped:
                        all_lines.append(stripped)
            else:
                # Fall back to OCR
                pix = page.get_pixmap()
                img_bytes = pix.tobytes("png")
                ocr_lines = _ocr_image_bytes(img_bytes)
                all_lines.extend(ocr_lines)
    finally:
        doc.close()

    raw_text = "\n".join(all_lines)
    return raw_text, all_lines


def _extract_image(image_bytes: bytes) -> Tuple[str, list[str]]:
    """Extract text from a single image using OCR."""
    ocr_lines = _ocr_image_bytes(image_bytes)
    raw_text = "\n".join(ocr_lines)
    return raw_text, ocr_lines
