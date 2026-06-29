"""
Warehouse OCR Router — FastAPI endpoints for warehouse document
processing.

Endpoints
---------
POST /api/v1/ocr/extract        — single document upload
POST /api/v1/ocr/extract-batch  — batch (multiple) document upload

Processing Pipeline (per file)
------------------------------
1. Validate file type & size
2. Run OCR (PaddleOCR + PyMuPDF)
3. Classify document type
4. Extract structured warehouse fields
5. Parse product rows
6. Validate extracted data
7. Build Django-ready storage payloads
8. Return standardised JSON response
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, File, UploadFile, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.database import get_db

from app.config import MAX_BATCH_FILES
from app.schemas import (
    BatchFileResult,
    BatchResponse,
    SingleDocumentResponse,
)
from app.services.classifier import calculate_extraction_confidence, classify_document
from app.services.field_extractor import extract_fields
from app.services.ocr_engine import run_ocr
from app.services.storage_mapper import build_storage_mapping, build_storage_payloads
from app.services.validator import validate_extracted_data
from app.services.db_storage import store_extracted_data_background
from app.utils.file_utils import validate_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ocr", tags=["Warehouse OCR"])


# ---------------------------------------------------------------------------
# Internal — process a single file through the full pipeline
# ---------------------------------------------------------------------------

def _process_single_file(file: UploadFile, background_tasks: BackgroundTasks, db: Session) -> SingleDocumentResponse:
    """Run the complete OCR pipeline on one uploaded file.

    Returns a fully populated SingleDocumentResponse (never raises).
    """
    logger.info("Received request to process file: %s", file.filename)
    response = SingleDocumentResponse(file_name=file.filename or "unknown")

    # --- Step 1: Validate file ---
    file_bytes, validation_errors = validate_file(file)
    if validation_errors:
        response.status = "failed"
        response.errors = validation_errors
        logger.warning("File validation failed for %s: %s", file.filename, validation_errors)
        return response

    try:
        # --- Step 2: Run OCR ---
        logger.info("Executing OCR text extraction for %s", file.filename)
        raw_text, ocr_lines = run_ocr(file_bytes, file.filename or "")
        response.raw_text = raw_text
        response.ocr_output = ocr_lines

        if not raw_text.strip():
            response.status = "failed"
            response.errors.append("OCR produced no text from this file.")
            logger.warning("OCR returned empty text stream for file: %s", file.filename)
            return response

        # --- Step 3: Classify document ---
        logger.info("Classifying document type for %s", file.filename)
        doc_type, classification_confidence = classify_document(raw_text)
        response.document_type = doc_type
        response.document_classification_confidence = classification_confidence
        logger.info("Document classified as '%s' (confidence: %.2f)", doc_type, classification_confidence)

        # --- Step 4 & 5: Extract fields + products ---
        logger.info("Extracting fields and tabular product data for %s", file.filename)
        extracted_data = extract_fields(raw_text, ocr_lines, doc_type)
        response.extracted_data = extracted_data

        # --- Step 5.5: Calculate extraction confidence ---
        extraction_confidence = calculate_extraction_confidence(
            extracted_data, doc_type, classification_confidence
        )
        response.extraction_confidence = extraction_confidence
        response.confidence_score = extraction_confidence

        # --- Step 6: Validate ---
        logger.info("Running business validation checks on extracted data for %s", file.filename)
        warnings, errors = validate_extracted_data(extracted_data, doc_type)
        response.warnings = warnings
        response.errors = errors
        if warnings:
            logger.info("Validation warnings found for %s: %s", file.filename, warnings)
        if errors:
            logger.warning("Validation errors found for %s: %s", file.filename, errors)

        # --- Step 7: Build storage payloads ---
        logger.info("Generating Django-ready storage payloads for %s", file.filename)
        response.storage_mapping = build_storage_mapping(doc_type)
        response.storage_payloads = build_storage_payloads(
            extracted_data=extracted_data,
            raw_text=raw_text,
            document_type=doc_type,
            file_name=file.filename or "unknown",
            confidence_score=extraction_confidence,
            document_classification_confidence=classification_confidence,
            extraction_confidence=extraction_confidence,
        )

        # Status is "success" even if there are warnings, but "failed" if
        # there are critical errors
        if errors:
            response.status = "partial"
        else:
            response.status = "success"

    except Exception as exc:
        response.status = "failed"
        response.errors.append(f"Processing error: {exc}")
        logger.error("Internal processing error for file %s: %s", file.filename, exc, exc_info=True)

    # --- Step 8: Queue Background DB Storage ---
    if response.status != "failed" and getattr(response, "extracted_data", None):
        logger.info("Queueing database storage background task for %s", file.filename)
        background_tasks.add_task(
            store_extracted_data_background,
            db,
            response.extracted_data,
            response.raw_text,
            response.document_type,
            response.file_name,
            response.confidence_score,
            response.status
        )

    return response



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/extract", response_model=SingleDocumentResponse)
def extract_single(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Upload and process a single warehouse document.

    Accepts PDF, PNG, JPG, or JPEG.  Returns structured extraction
    results with document classification, field extraction, product
    rows, validation warnings, and Django-ready storage payloads.
    """
    return _process_single_file(file, background_tasks, db)


@router.post("/extract-batch", response_model=BatchResponse)
def extract_batch(
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Upload and process multiple warehouse documents at once.

    Each file is processed independently — one failure does **not**
    stop the rest.  Accepts up to MAX_BATCH_FILES files per request.
    """
    batch = BatchResponse(total_files=len(files))

    # Guard against too many files
    if len(files) > MAX_BATCH_FILES:
        batch.status = "failed"
        batch.results.append(
            BatchFileResult(
                file_name="(batch)",
                status="failed",
                errors=[
                    f"Too many files. Maximum {MAX_BATCH_FILES} files per batch, got {len(files)}."
                ],
            )
        )
        batch.failed_files = len(files)
        return batch

    for file in files:
        result = _process_single_file(file, background_tasks, db)

        file_result = BatchFileResult(
            file_name=result.file_name,
            status=result.status,
            document_type=result.document_type,
            confidence_score=result.confidence_score,
            document_classification_confidence=result.document_classification_confidence,
            extraction_confidence=result.extraction_confidence,
            extracted_data=result.extracted_data,
            storage_mapping=result.storage_mapping,
            storage_payloads=result.storage_payloads,
            warnings=result.warnings,
            errors=result.errors,
        )
        batch.results.append(file_result)

        if result.status == "failed":
            batch.failed_files += 1
        else:
            batch.processed_files += 1

    # Overall batch status
    if batch.failed_files == batch.total_files:
        batch.status = "failed"
    elif batch.failed_files > 0:
        batch.status = "partial"
    else:
        batch.status = "success"

    return batch
