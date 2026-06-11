"""
Product-row parser for warehouse documents.

Attempts to detect tabular product data in OCR output and extract
individual product rows with SKU, name, quantities, dimensions,
weight, and batch/serial/barcode numbers.

Strategy
--------
1. Look for a "header line" that contains column-like keywords
   (e.g. "SKU", "Description", "Qty").
2. After the header, treat each subsequent non-empty line as a
   potential product row and try to parse columns out of it.
3. Also scan individual lines for labelled key-value patterns
   (e.g. "SKU: ABC123", "Batch No: XYZ").
4. Fall back to extracting any labelled values found anywhere in
   the text when no tabular structure is detected.
"""

from __future__ import annotations

import re
from typing import Optional

from app.schemas import ProductItem, Dimensions, Weight
from app.services.dimension_parser import parse_dimensions, parse_weight


# ---------------------------------------------------------------------------
# Header Detection
# ---------------------------------------------------------------------------

_HEADER_KEYWORDS = [
    "sku", "item", "product", "description", "material",
    "qty", "quantity", "uom", "unit", "rate", "price", "amount",
    "sl", "sr", "s.no", "sr.no", "sl.no", "#",
]

_HEADER_PATTERN = re.compile(
    r"|".join(re.escape(kw) for kw in _HEADER_KEYWORDS),
    re.IGNORECASE,
)


def _is_header_line(line: str) -> bool:
    """Return True if the line looks like a table header."""
    hits = len(_HEADER_PATTERN.findall(line))
    return hits >= 2


# ---------------------------------------------------------------------------
# Per-Line Value Extraction
# ---------------------------------------------------------------------------

def _extract_labelled(text: str, pattern: str) -> str:
    """Extract a value following a label pattern (case-insensitive)."""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _try_parse_number(text: str) -> Optional[float]:
    """Try to parse a string as a number; return None on failure."""
    if not text:
        return None
    text = text.replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


# Patterns for labelled fields typically found near product data
_SKU_PATTERN = r"(?:sku|item\s*code|material\s*code|product\s*code|part\s*no)[:\s#-]+([A-Za-z0-9_\-/]+)"
_BATCH_PATTERN = r"(?:batch\s*(?:no|number|#)|lot\s*(?:no|number|#))[:\s#-]+([A-Za-z0-9_\-/]+)"
_SERIAL_PATTERN = r"(?:serial\s*(?:no|number|#)|sr\s*no|s/n)[:\s#-]+([A-Za-z0-9_\-/]+)"
_BARCODE_PATTERN = r"(?:barcode|ean|upc|gtin)[:\s#-]+(\d[\d\s-]+\d)"
_QUANTITY_PATTERN = r"(?:qty|quantity)[:\s#-]+(\d+(?:\.\d+)?)"


# ---------------------------------------------------------------------------
# Tabular Row Parsing
# ---------------------------------------------------------------------------

def _parse_table_row(line: str) -> Optional[ProductItem]:
    """Attempt to extract product data from a single table row.

    Heuristic: split the line on two-or-more whitespace characters and
    try to map tokens to known column types.
    """
    # Split on 2+ spaces or tab — typical OCR table column separator
    tokens = re.split(r"\s{2,}|\t", line.strip())

    if len(tokens) < 2:
        return None

    product = ProductItem()

    # Try to identify numeric vs text tokens
    numeric_tokens: list[float] = []
    text_tokens: list[str] = []

    for token in tokens:
        num = _try_parse_number(token)
        if num is not None:
            numeric_tokens.append(num)
        else:
            text_tokens.append(token)

    # Need at least one text token (product name/sku) and one number (qty)
    if not text_tokens or not numeric_tokens:
        return None

    # First text token that looks like a code → SKU; otherwise → product_name
    for t in text_tokens:
        if re.match(r"^[A-Z0-9_\-/]{3,}$", t, re.IGNORECASE):
            if not product.sku:
                product.sku = t
            else:
                product.product_name = t
        else:
            if not product.product_name:
                product.product_name = t
            elif not product.sku:
                product.sku = t

    # First numeric token → quantity
    if numeric_tokens:
        product.quantity = numeric_tokens[0]
    if len(numeric_tokens) > 1:
        product.ordered_quantity = numeric_tokens[0]
        product.quantity = numeric_tokens[1]

    return product


# ---------------------------------------------------------------------------
# Full-Text Labelled Extraction (fallback)
# ---------------------------------------------------------------------------

def _extract_labelled_products(raw_text: str) -> list[ProductItem]:
    """Extract product info from labelled key-value lines (non-tabular).

    Useful for product labels or single-product documents.
    """
    sku = _extract_labelled(raw_text, _SKU_PATTERN)
    batch = _extract_labelled(raw_text, _BATCH_PATTERN)
    serial = _extract_labelled(raw_text, _SERIAL_PATTERN)
    barcode = _extract_labelled(raw_text, _BARCODE_PATTERN)
    qty_str = _extract_labelled(raw_text, _QUANTITY_PATTERN)
    qty = _try_parse_number(qty_str)

    dims = parse_dimensions(raw_text)
    weight = parse_weight(raw_text)

    # Only create a product if we found *something*
    if any([sku, batch, serial, barcode, qty is not None]):
        product = ProductItem(
            sku=sku,
            quantity=qty,
            batch_number=batch,
            serial_number=serial,
            barcode_number=barcode,
            dimensions=dims or Dimensions(),
            weight=weight or Weight(),
        )
        return [product]

    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_products(raw_text: str, ocr_lines: list[str]) -> list[ProductItem]:
    """Parse product rows from the OCR output.

    First tries to detect a table structure.  Falls back to labelled
    key-value extraction when no table header is found.
    """
    if not ocr_lines:
        return _extract_labelled_products(raw_text)

    products: list[ProductItem] = []
    header_found = False
    lines_after_header = 0

    for line in ocr_lines:
        if not header_found:
            if _is_header_line(line):
                header_found = True
            continue

        # Skip separator lines (dashes, equals, etc.)
        if re.match(r"^[\s\-=_|+]+$", line):
            continue

        # Stop after reasonable number of rows to avoid parsing footers
        lines_after_header += 1
        if lines_after_header > 100:
            break

        # Skip if line is too short to be a product row
        if len(line.strip()) < 5:
            continue

        product = _parse_table_row(line)
        if product:
            products.append(product)

    # If tabular parsing found nothing, try labelled extraction
    if not products:
        products = _extract_labelled_products(raw_text)

    # Enrich products with batch/serial/barcode from full text if not
    # already set (common when those appear outside the table)
    if products:
        batch = _extract_labelled(raw_text, _BATCH_PATTERN)
        serial = _extract_labelled(raw_text, _SERIAL_PATTERN)
        barcode = _extract_labelled(raw_text, _BARCODE_PATTERN)
        dims = parse_dimensions(raw_text)
        weight = parse_weight(raw_text)

        for p in products:
            if not p.batch_number and batch:
                p.batch_number = batch
            if not p.serial_number and serial:
                p.serial_number = serial
            if not p.barcode_number and barcode:
                p.barcode_number = barcode
            if p.dimensions.length is None and dims:
                p.dimensions = dims
            if p.weight.value is None and weight:
                p.weight = weight

    return products
