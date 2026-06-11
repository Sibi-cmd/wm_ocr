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
