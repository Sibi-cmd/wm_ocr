"""
File validation utilities for uploaded documents.

Checks file extension, MIME type, size, and emptiness before the
file enters the OCR pipeline.
"""

from __future__ import annotations

import os
from typing import Tuple

from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB


def get_file_extension(filename: str | None) -> str:
    """Return the lowercased file extension (e.g. '.pdf') or '' if missing."""
    if not filename:
        return ""
    return os.path.splitext(filename)[1].lower()


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
        return b"", errors

    if ext not in ALLOWED_EXTENSIONS:
        errors.append(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
        return b"", errors

    # --- Read bytes ---
    try:
        file_bytes = file.file.read()
    except Exception as exc:
        errors.append(f"Failed to read file: {exc}")
        return b"", errors

    # --- Check empty ---
    if not file_bytes:
        errors.append("Uploaded file is empty.")
        return b"", errors

    # --- Check size ---
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = round(len(file_bytes) / (1024 * 1024), 2)
        errors.append(
            f"File too large ({size_mb} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB."
        )
        return b"", errors

    return file_bytes, errors
