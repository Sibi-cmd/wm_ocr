"""
Document classifier — determines which warehouse document type the
extracted text belongs to using keyword scoring.

Each document type defined in ``app.config.DOCUMENT_KEYWORDS`` is
scored by counting how many of its keywords appear (case-insensitive)
in the raw OCR text.  The type with the highest score wins;
confidence is the normalised ratio of matched-keywords / total-keywords
for that type.
"""

from __future__ import annotations

from typing import Tuple

from app.config import DOCUMENT_KEYWORDS
from app.schemas import ExtractedData



def classify_document(raw_text: str) -> Tuple[str, float]:
    """Classify raw OCR text into a warehouse document type.

    Returns
    -------
    (document_type, confidence_score)
        document_type   : one of the keys in DOCUMENT_KEYWORDS, or "unknown"
        confidence_score: float between 0.0 and 1.0
    """
    if not raw_text or not raw_text.strip():
        return "unknown", 0.0

    text_lower = raw_text.lower()

    best_type = "unknown"
    best_score = 0          # absolute number of keyword hits
    best_confidence = 0.0   # hits / total_keywords for the winning type

    for doc_type, keywords in DOCUMENT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)

        if hits > best_score:
            best_score = hits
            best_type = doc_type
            best_confidence = round(hits / len(keywords), 2)

    # Require at least *one* keyword match to accept a classification
    if best_score == 0:
        return "unknown", 0.0

    return best_type, best_confidence


def calculate_extraction_confidence(
    data: ExtractedData,
    document_type: str,
    classification_confidence: float,
) -> float:
    """Calculate a weighted extraction confidence score (0.0 to 1.0) and cap at 1.00."""
    import re

    # 1. Required Fields (40%)
    req_vals = [
        data.document_info.invoice_number or data.document_info.document_number,
        data.document_info.document_date,
        data.party_info.supplier_name,
        data.party_info.buyer_name
    ]
    filled_req = sum(1 for val in req_vals if val)
    required_score = filled_req / 4.0

    # 2. Financial Fields (25%)
    fin_vals = [
        data.financial_info.subtotal,
        data.financial_info.tax,
        data.financial_info.total_amount
    ]
    filled_fin = sum(1 for val in fin_vals if val)
    financial_score = filled_fin / 3.0

    # 3. Product Fields (25%)
    if data.products:
        product_scores = []
        for p in data.products:
            p_fields = [
                p.product_name,
                p.sku,
                p.quantity is not None,
                p.dimensions.length is not None or p.dimensions.width is not None or p.dimensions.height is not None,
                p.weight.value is not None
            ]
            filled_p = sum(1 for f in p_fields if f)
            product_scores.append(filled_p / 5.0)
        product_score = sum(product_scores) / len(product_scores)
    else:
        if document_type in ("invoice", "grn", "purchase_order", "packing_list"):
            product_score = 0.0
        else:
            product_score = 1.0

    # 4. Classification Score (10%)
    classification_score = classification_confidence

    # 5. Optional Fields Bonus
    opt_fields = [
        data.shipment_info.vehicle_number,
        data.shipment_info.transporter_name,
        data.shipment_info.shipment_id,
        data.document_info.grn_number,
        data.shipment_info.carrier_name,
        data.shipment_info.delivery_date or data.document_info.delivery_number
    ]
    filled_opt = sum(1 for val in opt_fields if val)
    bonus = filled_opt * 0.02

    # 6. Final weighted calculation
    score = (
        required_score * 0.40 +
        financial_score * 0.25 +
        product_score * 0.25 +
        classification_score * 0.10
    ) + bonus

    return min(1.00, round(score, 2))

