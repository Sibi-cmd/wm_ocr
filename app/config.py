"""
Configuration constants for the Warehouse OCR service.

Centralises all tuneable settings: file limits, allowed types,
and keyword maps used by the document classifier.
"""

# ---------------------------------------------------------------------------
# File Upload Limits
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 20 MB

MAX_BATCH_FILES = 10

# ---------------------------------------------------------------------------
# Allowed File Types
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
}

# ---------------------------------------------------------------------------
# Document Classification Keyword Maps
# ---------------------------------------------------------------------------
# Each key is the canonical document type returned by the classifier.
# The value is a list of keywords/phrases (case-insensitive) that signal
# the document belongs to that type.  The classifier scores each type by
# counting how many of its keywords appear in the raw OCR text.
# ---------------------------------------------------------------------------
DOCUMENT_KEYWORDS: dict[str, list[str]] = {
    "purchase_order": [
        "purchase order",
        "po number",
        "po no",
        "po#",
        "ordered quantity",
        "order quantity",
        "buyer",
        "supplier",
        "purchase requisition",
        "order date",
        "delivery schedule",
    ],
    "invoice": [
        "tax invoice",
        "invoice number",
        "invoice no",
        "invoice#",
        "inv no",
        "gst",
        "gstin",
        "total amount",
        "net amount",
        "due date",
        "payment terms",
        "bill to",
        "ship to",
        "taxable value",
        "cgst",
        "sgst",
        "igst",
        "hsn",
    ],
    "packing_list": [
        "packing list",
        "package id",
        "shipment id",
        "carton dimensions",
        "carton no",
        "package number",
        "gross weight",
        "net weight",
        "total packages",
        "total cartons",
        "marks and numbers",
    ],
    "delivery_note": [
        "delivery note",
        "delivery challan",
        "challan no",
        "challan number",
        "vehicle number",
        "vehicle no",
        "transporter",
        "transport",
        "carrier",
        "lr number",
        "lr no",
        "consignment",
        "dispatch",
        "dispatched",
    ],
    "grn": [
        "goods receipt note",
        "goods receipt",
        "grn number",
        "grn no",
        "grn#",
        "received quantity",
        "damaged quantity",
        "accepted quantity",
        "rejected quantity",
        "inspection",
        "receiving report",
        "inward",
    ],
    "product_label": [
        "barcode",
        "serial number",
        "serial no",
        "batch number",
        "batch no",
        "lot number",
        "lot no",
        "manufacturing date",
        "mfg date",
        "expiry date",
        "exp date",
        "ean",
        "upc",
        "sku",
    ],
}

# All supported document types (for validation / display)
SUPPORTED_DOCUMENT_TYPES = list(DOCUMENT_KEYWORDS.keys()) + ["unknown"]
