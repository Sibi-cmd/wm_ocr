"""
Pydantic response & data models for the Warehouse OCR service.

These schemas define the exact JSON shapes returned by the
/api/v1/ocr/extract and /api/v1/ocr/extract-batch endpoints,
matching the contract expected by the Django backend.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Nested Data Structures
# ---------------------------------------------------------------------------

class Dimensions(BaseModel):
    """Physical dimensions of a product or package."""
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    unit: str = "cm"


class Weight(BaseModel):
    """Weight measurement of a product or package."""
    value: Optional[float] = None
    unit: str = "kg"


class ProductItem(BaseModel):
    """A single product row extracted from the document."""
    sku: str = ""
    product_name: str = ""
    category: str = ""
    quantity: Optional[float] = None
    ordered_quantity: Optional[float] = None
    received_quantity: Optional[float] = None
    damaged_quantity: Optional[float] = None
    unit: str = ""
    dimensions: Dimensions = Field(default_factory=Dimensions)
    weight: Weight = Field(default_factory=Weight)
    batch_number: str = ""
    serial_number: str = ""
    barcode_number: str = ""


# ---------------------------------------------------------------------------
# Extracted Data — grouped by domain
# ---------------------------------------------------------------------------

class DocumentInfo(BaseModel):
    """Core identifiers found on the document."""
    document_number: str = ""
    document_date: str = ""
    po_number: str = ""
    invoice_number: str = ""
    delivery_number: str = ""
    grn_number: str = ""


class PartyInfo(BaseModel):
    """Supplier / buyer / warehouse details."""
    supplier_name: str = ""
    supplier_id: str = ""
    buyer_name: str = ""
    warehouse_name: str = ""


class ShipmentInfo(BaseModel):
    """Transport and shipping details."""
    shipment_id: str = ""
    vehicle_number: str = ""
    carrier_name: str = ""
    transporter_name: str = ""
    delivery_date: str = ""


class FinancialInfo(BaseModel):
    """Monetary values extracted from the document."""
    unit_price: str = ""
    subtotal: str = ""
    tax: str = ""
    total_amount: str = ""


class ReceiptInfo(BaseModel):
    """Goods-receipt specific quantities and remarks."""
    received_quantity: str = ""
    damaged_quantity: str = ""
    accepted_quantity: str = ""
    remarks: str = ""


class ExtractedData(BaseModel):
    """All structured data extracted from a single warehouse document."""
    document_info: DocumentInfo = Field(default_factory=DocumentInfo)
    party_info: PartyInfo = Field(default_factory=PartyInfo)
    products: list[ProductItem] = Field(default_factory=list)
    shipment_info: ShipmentInfo = Field(default_factory=ShipmentInfo)
    financial_info: FinancialInfo = Field(default_factory=FinancialInfo)
    receipt_info: ReceiptInfo = Field(default_factory=ReceiptInfo)


# ---------------------------------------------------------------------------
# Storage Mapping — tells Django *what to do* with the extracted data
# ---------------------------------------------------------------------------

class StorageMapping(BaseModel):
    """Flags consumed by the Django backend to decide which tables to write."""
    save_original_json_to: str = "ocr_documents.extracted_json"
    save_raw_text_to: str = "ocr_documents.raw_text"
    create_or_update_products: bool = True
    create_inbound_receipt: bool = True
    create_inbound_items: bool = True
    ready_for_putaway_recommendation: bool = True


# ---------------------------------------------------------------------------
# Storage Payloads — pre-built dicts the Django backend can persist directly
# ---------------------------------------------------------------------------

class StoragePayloads(BaseModel):
    """Ready-to-persist payloads for each Django model / table."""
    ocr_document_payload: dict[str, Any] = Field(default_factory=dict)
    product_payload: list[dict[str, Any]] = Field(default_factory=list)
    inbound_receipt_payload: dict[str, Any] = Field(default_factory=dict)
    inbound_items_payload: list[dict[str, Any]] = Field(default_factory=list)
    shipment_payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-Level Response Models
# ---------------------------------------------------------------------------

class SingleDocumentResponse(BaseModel):
    """Full response returned by POST /api/v1/ocr/extract."""
    status: str = "success"
    file_name: str = ""
    document_type: str = "unknown"
    confidence_score: float = 0.0
    document_classification_confidence: float = 0.0
    extraction_confidence: float = 0.0
    raw_text: str = ""
    ocr_output: list[str] = Field(default_factory=list)
    extracted_data: ExtractedData = Field(default_factory=ExtractedData)
    storage_mapping: StorageMapping = Field(default_factory=StorageMapping)
    storage_payloads: StoragePayloads = Field(default_factory=StoragePayloads)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BatchFileResult(BaseModel):
    """Per-file result within a batch response."""
    file_name: str = ""
    status: str = "success"
    document_type: str = "unknown"
    confidence_score: float = 0.0
    document_classification_confidence: float = 0.0
    extraction_confidence: float = 0.0
    extracted_data: ExtractedData = Field(default_factory=ExtractedData)
    storage_mapping: StorageMapping = Field(default_factory=StorageMapping)
    storage_payloads: StoragePayloads = Field(default_factory=StoragePayloads)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BatchResponse(BaseModel):
    """Full response returned by POST /api/v1/ocr/extract-batch."""
    status: str = "success"
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    results: list[BatchFileResult] = Field(default_factory=list)
