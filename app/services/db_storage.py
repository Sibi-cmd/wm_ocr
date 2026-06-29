"""
Database Storage Service
Handles background persistence of OCR results directly to Neon DB.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models import OCRDocument, Product, ProductDimension, ProductStorageRule
from app.schemas import ExtractedData
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def store_extracted_data_background(
    db: Session,
    extracted_data: ExtractedData,
    raw_text: str,
    document_type: str,
    file_name: str = "unknown",
    confidence_score: Optional[float] = None,
    processing_status: str = "SUCCESS"
):
    """
    Safely stores the OCR extracted data into the database in a background task.
    Uses a fresh transaction context (SessionLocal) to prevent request-lifecycle closed connection issues.
    Saves document status as 'PROCESSING' first, then commits products, and updates status to FAILED on error.
    """
    logger.info("Starting background database persistence of OCR document: %s", file_name)
    
    session = SessionLocal()
    ocr_doc_id = None
    
    try:
        # Calculate document hash
        raw_bytes = raw_text.encode('utf-8') if raw_text else b""
        doc_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 1. Create and persist the initial OCRDocument record
        ocr_doc = OCRDocument(
            document_type=document_type or "unknown",
            raw_text=raw_text or "",
            extracted_json=extracted_data.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            confidence_score=confidence_score,
            document_hash=doc_hash,
            file_name=file_name or "unknown",
            file_path=f"uploads/{file_name or 'unknown'}",
            processing_status="PROCESSING",
            error_message=None,
            rejection_reason=None
        )
        session.add(ocr_doc)
        session.commit()
        ocr_doc_id = ocr_doc.ocr_id
        logger.info("Initialized OCRDocument record in DB with status PROCESSING. ID: %s", ocr_doc_id)
        
    except Exception as e:
        session.rollback()
        logger.critical(
            "Failed to create initial OCRDocument record in DB for file %s: %s",
            file_name,
            e,
            exc_info=True
        )
        session.close()
        return

    # 2. Iterate and persist extracted products and dimensions
    try:
        for p in extracted_data.products:
            sku = p.sku.strip()
            # If no SKU was extracted, we cannot reliably store or link the product
            if not sku:
                continue

            # Check if product exists
            product = session.query(Product).filter(Product.sku == sku).first()
            is_new_product = False
            
            if not product:
                is_new_product = True
                product = Product(
                    sku=sku,
                    product_name=p.product_name or f"Unknown Product ({sku})",
                    weight=p.weight.value if p.weight and p.weight.value else None
                )
                session.add(product)
                session.flush()  # To generate product_id

            # 3. Store Dimensions (Only if extracted)
            has_dimensions = (p.dimensions.length is not None or 
                              p.dimensions.width is not None or 
                              p.dimensions.height is not None)
            
            if has_dimensions:
                dim_record = session.query(ProductDimension).filter(ProductDimension.product_id == product.product_id).first()
                if not dim_record:
                    dim_record = ProductDimension(product_id=product.product_id)
                    session.add(dim_record)
                
                # Update dimensions, only overwriting if OCR found something
                if p.dimensions.length is not None:
                    dim_record.length = p.dimensions.length
                if p.dimensions.width is not None:
                    dim_record.width = p.dimensions.width
                if p.dimensions.height is not None:
                    dim_record.height = p.dimensions.height

            # 4. Store Storage Rules (Apply defaults for new products to satisfy relations)
            if is_new_product:
                # Add default storage rules for the newly discovered product
                rule_record = ProductStorageRule(
                    product_id=product.product_id,
                    allowed_zone_type="MEDIUM",
                    max_stack_height=5,
                    orientation_rule="UPRIGHT_ONLY"
                )
                session.add(rule_record)

        # Update OCRDocument status to final status
        ocr_doc = session.query(OCRDocument).filter(OCRDocument.ocr_id == ocr_doc_id).first()
        if ocr_doc:
            ocr_doc.processing_status = (processing_status or "SUCCESS").upper()
            ocr_doc.updated_at = datetime.now(timezone.utc)
        
        session.commit()
        logger.info(
            "Successfully completed database persistence of products for OCRDocument ID: %s (Status: %s)",
            ocr_doc_id,
            processing_status
        )

    except Exception as e:
        session.rollback()
        logger.error(
            "Database transaction failed for products linked to OCRDocument ID: %s. Setting status to FAILED. Details: %s",
            ocr_doc_id,
            e,
            exc_info=True
        )
        
        # In a separate transaction context, record the failure details on the OCRDocument
        try:
            ocr_doc = session.query(OCRDocument).filter(OCRDocument.ocr_id == ocr_doc_id).first()
            if ocr_doc:
                ocr_doc.processing_status = "FAILED"
                ocr_doc.error_message = f"Database write failure: {e}"
                ocr_doc.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.info("Successfully updated database status to FAILED for OCRDocument ID: %s", ocr_doc_id)
        except Exception as inner_e:
            session.rollback()
            logger.critical(
                "Failed to update OCRDocument status to FAILED in DB: %s",
                inner_e,
                exc_info=True
            )
            
    finally:
        session.close()

