"""
Validation layer for extracted warehouse data.

Checks business rules and returns lists of warnings and errors.
Warnings are non-blocking (data is still returned); errors indicate
that a field is critically invalid.
"""

from __future__ import annotations

import re
from typing import Tuple

from app.schemas import ExtractedData


def validate_extracted_data(
    data: ExtractedData,
    document_type: str,
) -> Tuple[list[str], list[str]]:
    """Validate the extracted data against business rules.

    Returns
    -------
    (warnings, errors)
        warnings : list of non-blocking issues (data still usable)
        errors   : list of critical issues
    """
    warnings: list[str] = []
    errors: list[str] = []

    # -----------------------------------------------------------------------
    # Party Info
    # -----------------------------------------------------------------------
    if not data.party_info.supplier_name:
        warnings.append("Missing supplier name.")
    if not data.party_info.buyer_name:
        warnings.append("Missing buyer name.")
    if not data.party_info.warehouse_name:
        warnings.append("Missing warehouse name.")

    # -----------------------------------------------------------------------
    # Document Info
    # -----------------------------------------------------------------------
    if not data.document_info.document_number:
        warnings.append("Missing document number.")
    if not data.document_info.document_date:
        warnings.append("Missing document date.")

    # Date format check — should be YYYY-MM-DD after normalisation
    if data.document_info.document_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", data.document_info.document_date):
            warnings.append(
                f"Document date '{data.document_info.document_date}' is not in YYYY-MM-DD format."
            )

    # -----------------------------------------------------------------------
    # Product Rows
    # -----------------------------------------------------------------------
    if not data.products:
        warnings.append("No product rows detected.")
    else:
        for idx, product in enumerate(data.products, start=1):
            label = f"Product row {idx}"

            # SKU should not be empty if product row exists
            if not product.sku:
                warnings.append(f"{label}: Missing SKU.")

            # Quantity must be numeric (it already is float | None from schema)
            if product.quantity is not None and product.quantity < 0:
                errors.append(f"{label}: Quantity must be non-negative, got {product.quantity}.")

            if product.ordered_quantity is not None and product.ordered_quantity < 0:
                errors.append(f"{label}: Ordered quantity must be non-negative.")

            if product.received_quantity is not None and product.received_quantity < 0:
                errors.append(f"{label}: Received quantity must be non-negative.")

            if product.damaged_quantity is not None and product.damaged_quantity < 0:
                errors.append(f"{label}: Damaged quantity must be non-negative.")

            # Dimensions must be positive
            dims = product.dimensions
            for dim_name in ("length", "width", "height"):
                val = getattr(dims, dim_name, None)
                if val is not None and val <= 0:
                    errors.append(
                        f"{label}: Dimension '{dim_name}' must be positive, got {val}."
                    )

            if dims.length is None and dims.width is None and dims.height is None:
                warnings.append(f"{label}: Missing dimensions.")

            # Weight must be positive
            if product.weight.value is not None and product.weight.value <= 0:
                errors.append(
                    f"{label}: Weight must be positive, got {product.weight.value}."
                )

            if product.weight.value is None:
                warnings.append(f"{label}: Missing weight.")

    # -----------------------------------------------------------------------
    # Shipment Info — contextual checks
    # -----------------------------------------------------------------------
    if document_type in ("delivery_note", "packing_list"):
        if not data.shipment_info.vehicle_number:
            warnings.append("Missing vehicle number (expected for delivery note / packing list).")
        if not data.shipment_info.delivery_date:
            warnings.append("Missing delivery date.")

    # -----------------------------------------------------------------------
    # Financial Info — contextual checks
    # -----------------------------------------------------------------------
    if document_type == "invoice":
        if not data.financial_info.total_amount:
            warnings.append("Missing total amount (expected for invoice).")

    # -----------------------------------------------------------------------
    # Receipt Info — contextual checks
    # -----------------------------------------------------------------------
    if document_type == "grn":
        if not data.receipt_info.received_quantity:
            warnings.append("Missing received quantity (expected for GRN).")

    return warnings, errors
