"""
File validation utilities for uploaded documents.

Checks file extension, MIME type, size, and emptiness before the
file enters the OCR pipeline.
"""

from __future__ import annotations

import os
import logging
from typing import Tuple

from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)


def get_file_extension(filename: str | None) -> str:
    """Return the lowercased file extension (e.g. '.pdf') or '' if missing."""
    if not filename:
        return ""
    return os.path.splitext(filename)[1].lower()


def validate_magic_bytes(file_bytes: bytes) -> Tuple[str | None, str | None]:
    """Verify magic bytes of the file content and return (detected_mime, detected_ext)."""
    if file_bytes.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    return None, None


def validate_file(file: UploadFile) -> Tuple[bytes, list[str]]:
    """Read and validate an uploaded file.

    Returns
    -------
    (file_bytes, errors)
        file_bytes : raw bytes (empty if validation failed)
        errors     : list of human-readable error strings (empty if OK)
    """
    errors: list[str] = []

    # --- Check filename / extension ---
    filename = file.filename or ""
    ext = get_file_extension(filename)

    if not ext:
        errors.append("File has no extension. Supported: PDF, PNG, JPG, JPEG.")
        logger.warning("Validation failed for file %s: Missing file extension.", filename)
        return b"", errors

    if ext not in ALLOWED_EXTENSIONS:
        errors.append(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
        logger.warning("Validation failed for file %s: Unsupported extension '%s'.", filename, ext)
        return b"", errors

    # --- Read bytes ---
    try:
        file_bytes = file.file.read()
    except Exception as exc:
        errors.append(f"Failed to read file: {exc}")
        logger.error("Failed to read file %s: %s", filename, exc, exc_info=True)
        return b"", errors

    # --- Check empty ---
    if not file_bytes:
        errors.append("Uploaded file is empty.")
        logger.warning("Validation failed for file %s: File is empty.", filename)
        return b"", errors


    # --- Check magic bytes to prevent MIME spoofing ---
    detected_mime, detected_ext = validate_magic_bytes(file_bytes)
    if not detected_mime or not detected_ext:
        errors.append(
            "File signature mismatch. The file content does not match any allowed format (PDF, PNG, JPEG)."
        )
        logger.warning(
            "Validation failed for file %s: Invalid magic bytes. Detected mime: %s.",
            filename,
            detected_mime
        )
        return b"", errors

    # Check extension mismatch
    ext_clean = ext.lower().replace(".jpeg", ".jpg")
    det_ext_clean = detected_ext.lower().replace(".jpeg", ".jpg")
    if ext_clean != det_ext_clean:
        errors.append(
            f"MIME spoofing detected. File extension '{ext}' does not match the actual file content format '{detected_ext}'."
        )
        logger.warning(
            "Validation failed for file %s: Spoofing detected. Extension is %s, magic bytes detect %s.",
            filename,
            ext,
            detected_ext
        )
        return b"", errors

    # --- Check size ---
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = round(len(file_bytes) / (1024 * 1024), 2)
        errors.append(
            f"File too large ({size_mb} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB."
        )
        logger.warning("Validation failed for file %s: Size %s MB exceeds limit.", filename, size_mb)
        return b"", errors

    logger.info("Successfully validated file %s (MIME: %s, size: %d bytes)", filename, detected_mime, len(file_bytes))
    return file_bytes, errors

