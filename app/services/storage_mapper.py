"""
Storage mapper — builds Django-ready payloads from extracted data.

The OCR service does NOT write to the database.  Instead it
prepares structured payloads that the Django backend can persist
directly into the appropriate tables:

    ocr_documents   → extracted_json  (JSONB)  +  raw_text
    products        → product rows
    inbound_receipts → receipt header
    inbound_items   → line items per receipt
    shipments       → transport details
"""

from __future__ import annotations

from typing import Any

from app.schemas import ExtractedData, StorageMapping, StoragePayloads


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_storage_mapping(document_type: str) -> StorageMapping:
    """Return a StorageMapping with sensible defaults for the document type."""
    mapping = StorageMapping()

    # Not all document types create all entities
    if document_type == "product_label":
        mapping.create_inbound_receipt = False
        mapping.create_inbound_items = False
        mapping.ready_for_putaway_recommendation = False

    if document_type == "invoice":
        mapping.ready_for_putaway_recommendation = False

    return mapping


def build_storage_payloads(
    extracted_data: ExtractedData,
    raw_text: str,
    document_type: str,
    file_name: str,
    confidence_score: float,
) -> StoragePayloads:
    """Build all 5 Django-ready payloads from the extracted data.

    These payloads match the shapes expected by the Django serialisers
    for each destination table.
    """
    payloads = StoragePayloads()

    # -------------------------------------------------------------------
    # 1. OCR Document Payload → ocr_documents table
    # -------------------------------------------------------------------
    payloads.ocr_document_payload = {
        "file_name": file_name,
        "document_type": document_type,
        "confidence_score": confidence_score,
        "raw_text": raw_text,
        "extracted_json": extracted_data.model_dump(),
    }

    # -------------------------------------------------------------------
    # 2. Product Payload → products table
    # -------------------------------------------------------------------
    payloads.product_payload = []
    for product in extracted_data.products:
        payloads.product_payload.append({
            "sku": product.sku,
            "product_name": product.product_name,
            "category": product.category,
            "unit": product.unit,
            "dimensions": product.dimensions.model_dump(),
            "weight": product.weight.model_dump(),
            "batch_number": product.batch_number,
            "serial_number": product.serial_number,
            "barcode_number": product.barcode_number,
        })

    # -------------------------------------------------------------------
    # 3. Inbound Receipt Payload → inbound_receipts table
    # -------------------------------------------------------------------
    doc_info = extracted_data.document_info
    party_info = extracted_data.party_info
    receipt_info = extracted_data.receipt_info

    payloads.inbound_receipt_payload = {
        "document_type": document_type,
        "document_number": doc_info.document_number,
        "document_date": doc_info.document_date,
        "po_number": doc_info.po_number,
        "invoice_number": doc_info.invoice_number,
        "delivery_number": doc_info.delivery_number,
        "grn_number": doc_info.grn_number,
        "supplier_name": party_info.supplier_name,
        "supplier_id": party_info.supplier_id,
        "buyer_name": party_info.buyer_name,
        "warehouse_name": party_info.warehouse_name,
        "received_quantity": receipt_info.received_quantity,
        "damaged_quantity": receipt_info.damaged_quantity,
        "accepted_quantity": receipt_info.accepted_quantity,
        "remarks": receipt_info.remarks,
    }

    # -------------------------------------------------------------------
    # 4. Inbound Items Payload → inbound_items table
    # -------------------------------------------------------------------
    payloads.inbound_items_payload = []
    for product in extracted_data.products:
        payloads.inbound_items_payload.append({
            "sku": product.sku,
            "product_name": product.product_name,
            "quantity": product.quantity,
            "ordered_quantity": product.ordered_quantity,
            "received_quantity": product.received_quantity,
            "damaged_quantity": product.damaged_quantity,
            "accepted_quantity": product.quantity,  # default to full qty
            "unit": product.unit,
            "batch_number": product.batch_number,
            "serial_number": product.serial_number,
            "barcode_number": product.barcode_number,
        })

    # -------------------------------------------------------------------
    # 5. Shipment Payload → shipments table
    # -------------------------------------------------------------------
    ship = extracted_data.shipment_info
    payloads.shipment_payload = {
        "shipment_id": ship.shipment_id,
        "vehicle_number": ship.vehicle_number,
        "carrier_name": ship.carrier_name,
        "transporter_name": ship.transporter_name,
        "delivery_date": ship.delivery_date,
        "po_number": doc_info.po_number,
        "invoice_number": doc_info.invoice_number,
        "supplier_name": party_info.supplier_name,
    }

    return payloads
