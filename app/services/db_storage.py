"""
Database Storage Service
Handles background persistence of OCR results directly to Neon DB.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
import uuid

from app.models import OCRDocument, Product, ProductDimension, ProductStorageRule
from app.schemas import ExtractedData

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
    Wrapped in a transaction to prevent partial data states.
    Strictly avoids inserting missing or completely empty dimension/rule rows.
    """
    try:
        # Calculate document hash
        raw_bytes = raw_text.encode('utf-8') if raw_text else b""
        doc_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 1. Store the full OCR result
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
            processing_status=(processing_status or "SUCCESS").upper(),
            error_message=None,
            rejection_reason=None
        )
        db.add(ocr_doc)

        # 2. Iterate through extracted products
        for p in extracted_data.products:
            sku = p.sku.strip()
            # If no SKU was extracted, we cannot reliably store or link the product
            if not sku:
                continue

            # Check if product exists
            product = db.query(Product).filter(Product.sku == sku).first()
            is_new_product = False
            
            if not product:
                is_new_product = True
                product = Product(
                    sku=sku,
                    product_name=p.product_name or f"Unknown Product ({sku})",
                    weight=p.weight.value if p.weight and p.weight.value else None
                )
                db.add(product)
                db.flush()  # To generate product_id

            # 3. Store Dimensions (Only if extracted)
            has_dimensions = (p.dimensions.length is not None or 
                              p.dimensions.width is not None or 
                              p.dimensions.height is not None)
            
            if has_dimensions:
                dim_record = db.query(ProductDimension).filter(ProductDimension.product_id == product.product_id).first()
                if not dim_record:
                    dim_record = ProductDimension(product_id=product.product_id)
                    db.add(dim_record)
                
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
                db.add(rule_record)

        # Commit transaction once everything is successfully staged
        db.commit()

    except Exception as e:
        # Rollback on any error to prevent partial commits
        db.rollback()
        # In a real system, you'd log this exception
        print(f"Failed to store OCR data in DB: {e}")
