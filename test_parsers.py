import pytest
from app.services.field_extractor import _extract_party_info
from app.services.dimension_parser import parse_dimensions, parse_weight
from app.services.product_parser import parse_products

def test_supplier_variations():
    # 1. Supplier variations
    for label in ["Supplier: ABC Electronics Private Limited", 
                  "Supplier Name: ABC Electronics Private Limited", 
                  "Supplier Information: ABC Electronics Private Limited"]:
        party = _extract_party_info(label)
        assert party.supplier_name == "ABC Electronics Private Limited"

    # Backward compatibility with dot separator
    party = _extract_party_info("Supplier. ABC Electronics Pvt Ltd")
    assert party.supplier_name == "ABC Electronics Pvt Ltd"

def test_buyer_variations():
    # 2. Buyer variations
    for label in ["Buyer: XYZ Warehouse Solutions", 
                  "Buyer Name: XYZ Warehouse Solutions", 
                  "Buyer Information: XYZ Warehouse Solutions"]:
        party = _extract_party_info(label)
        assert party.buyer_name == "XYZ Warehouse Solutions"

    # Backward compatibility with suyer
    party = _extract_party_info("Suyer: XYZ Warehouse Solutions")
    assert party.buyer_name == "XYZ Warehouse Solutions"

def test_warehouse_variations():
    # 3. Warehouse variations
    for label in ["Warehouse: Main Warehouse", 
                  "Warehouse Name: Main Warehouse"]:
        party = _extract_party_info(label)
        assert party.warehouse_name == "Main Warehouse"

def test_dimension_variations():
    # 4. Multi-line dimensions
    text_multi = "Length: 25 cm\nWidth: 12 cm\nHeight: 8 cm"
    dims = parse_dimensions(text_multi)
    assert dims is not None
    assert dims.length == 25.0
    assert dims.width == 12.0
    assert dims.height == 8.0
    assert dims.unit == "cm"

    # 5. Compact dimensions
    text_compact = "25 x 12 x 8 cm"
    dims = parse_dimensions(text_compact)
    assert dims is not None
    assert dims.length == 25.0
    assert dims.width == 12.0
    assert dims.height == 8.0
    assert dims.unit == "cm"

def test_weight_variations():
    # 6. Weight standard and 7. Alternate labels
    for label in ["Weight: 1.2 kg", "WT: 1.2 kg", "WGT: 1.2 kg"]:
        weight = parse_weight(label)
        assert weight is not None
        assert weight.value == 1.2
        assert weight.unit == "kg"

    # SKU digits isolation: SKU and quantity should NOT match weight
    # when WT/Weight label is missing but there is some text that looks like a number + g
    text_sku_only = "SKU: SCN-1001\nQuantity: 10"
    weight = parse_weight(text_sku_only)
    assert weight is None or weight.value != 1001

def test_product_name_and_category():
    # Product name variations (Product Name, Name, Description)
    for name_label in ["Product Name: Wireless Barcode Scanner", 
                       "Name: Wireless Barcode Scanner", 
                       "Description: Wireless Barcode Scanner"]:
        text = f"SKU: SCN-1001\n{name_label}\nCategory: Electronics\nQuantity: 10"
        products = parse_products(text, text.splitlines())
        assert len(products) == 1
        assert products[0].sku == "SCN-1001"
        assert products[0].product_name == "Wireless Barcode Scanner"
        assert products[0].category == "Electronics"

def test_multi_product_invoice():
    ocr_text = """
Supplier Name: ABC Electronics Private Limited
Warehouse Name: Main Warehouse

Product 1
SKU: SCN-1001
Product Name: Wireless Barcode Scanner
Category: Electronics
Quantity: 10
Length: 25 cm
Width: 12 cm
Height: 8 cm
Weight: 1.2 kg

Product 2
SKU: RFID-2001
Product Name: RFID Reader
Category: Electronics
Quantity: 5
Length: 40 cm
Width: 25 cm
Height: 15 cm
Weight: 3.5 kg

Product 3
SKU: PRN-3001
Product Name: Thermal Label Printer
Category: Warehouse Equipment
Quantity: 2
Length: 50 cm
Width: 30 cm
Height: 25 cm
Weight: 8 kg
"""
    products = parse_products(ocr_text, ocr_text.splitlines())
    assert len(products) == 3
    
    assert products[0].sku == "SCN-1001"
    assert products[0].product_name == "Wireless Barcode Scanner"
    assert products[0].category == "Electronics"
    assert products[0].quantity == 10
    assert products[0].dimensions.length == 25.0
    assert products[0].dimensions.width == 12.0
    assert products[0].dimensions.height == 8.0
    assert products[0].dimensions.unit == "cm"
    assert products[0].weight.value == 1.2
    assert products[0].weight.unit == "kg"

    assert products[1].sku == "RFID-2001"
    assert products[1].product_name == "RFID Reader"
    assert products[1].category == "Electronics"
    assert products[1].quantity == 5

    assert products[2].sku == "PRN-3001"
    assert products[2].product_name == "Thermal Label Printer"
    assert products[2].category == "Warehouse Equipment"
    assert products[2].quantity == 2

def test_warehouse_solutions_no_solutions():
    # Regression test: XYZ Warehouse Solutions should NOT extract "Solutions" as warehouse name
    party = _extract_party_info("Buyer: XYZ Warehouse Solutions")
    assert party.warehouse_name == ""

def test_header_row_not_product():
    # Regression test: Header rows should never be parsed as products
    header_lines = [
        "SKU Description Qty Rate Amount",
        "SKU\tDescription\tQty\tRate\tAmount",
        "SKU Description Quantity Price Total"
    ]
    for line in header_lines:
        products = parse_products("", [line])
        assert len(products) == 0

def test_product_tabular_validation():
    # Test correct parsing with separate columns and correct mathematical check
    line1 = "LAPTOP001 Dell Latitude 5450 100 50000 5000000"
    line2 = "MOUSE002 Logitech MX Master 200 3500 700000"
    
    products1 = parse_products("", [line1])
    assert len(products1) == 1
    assert products1[0].sku == "LAPTOP001"
    assert products1[0].product_name == "Dell Latitude 5450"
    assert products1[0].quantity == 100.0
    
    products2 = parse_products("", [line2])
    assert len(products2) == 1
    assert products2[0].sku == "MOUSE002"
    assert products2[0].product_name == "Logitech MX Master"
    assert products2[0].quantity == 200.0

    # Verify that mathematical constraint is checked: quantity * unit_price == total_price
    # Incorrect math row should be rejected
    line_incorrect = "LAPTOP001 Dell Latitude 5450 100 50000 9999999"
    products_incorrect = parse_products("", [line_incorrect])
    assert len(products_incorrect) == 0

def test_product_merged_and_collapsed_validation():
    # Test merged token at the end of the line
    line = "MOUSE002 Logitech MX Master2003500700000"
    products = parse_products("", [line])
    assert len(products) == 1
    assert products[0].sku == "MOUSE002"
    assert products[0].product_name == "Logitech MX Master"
    assert products[0].quantity == 200.0

def test_fuzzy_matching_and_first_character_drops():
    from app.services.field_extractor import _extract_document_info, _extract_shipment_info, _extract_financial_info
    
    # 1. Invoice -> nvoice
    doc = _extract_document_info("nvoice Number. INV-2026-001\nnvoice Date: 11/06/2026", "invoice")
    assert doc.invoice_number == "INV-2026-001"
    assert doc.document_date == "2026-06-11"
    
    # 2. Vehicle -> ehicle
    ship = _extract_shipment_info("ehicle Number: KA-01-AB-1234")
    assert ship.vehicle_number == "KA-01-AB-1234"
    
    # 3. Transporter -> ransporter
    ship2 = _extract_shipment_info("ransporter: BlueDart Express")
    assert ship2.transporter_name == "BlueDart Express"
    
    # 4. Total Amount -> otal Amount
    fin = _extract_financial_info("otal Amount 6726000")
    assert fin.total_amount == "6726000"
    
    # 5. GST (18%) -> tax
    fin2 = _extract_financial_info("GST (18%): 1026000")
    assert fin2.tax == "1026000"


def test_new_parser_improvements():
    from app.services.field_extractor import _extract_party_info, _normalise_date
    from app.services.product_parser import parse_products

    # 1. Nesting and multi-line label tests
    text_nested = """
Supplier Information
Supplier Name: ABC Electronics Private Limited

Buyer Information
Warehouse Name: Main Warehouse
"""
    party = _extract_party_info(text_nested)
    assert party.supplier_name == "ABC Electronics Private Limited"
    assert party.buyer_name == "Main Warehouse"
    assert party.warehouse_name == "Main Warehouse"

    # 2. Verify "Information" is never returned as supplier or buyer name
    texts_with_info = [
        "Supplier Information\nABC Electronics Private Limited",
        "Buyer Information\nMain Warehouse",
        "Supplier Info\nABC Electronics Private Limited",
        "Buyer Info: Main Warehouse"
    ]
    for txt in texts_with_info:
        p = _extract_party_info(txt)
        assert p.supplier_name != "Information"
        assert p.supplier_name != "Info"
        assert p.buyer_name != "Information"
        assert p.buyer_name != "Info"

    # 3. Space-separated date normalization
    assert _normalise_date("2026 06 17") == "2026-06-17"
    assert _normalise_date("2026  06  17") == "2026-06-17"
    
    # 4. Unlabelled product blocks
    text_products = """
Product 1
SKU: SCN-1001
Wireless Barcode Scanner
Category: Electronics
Quantity: 10

Product 2
SKU: RFID-2001
RFID Reader
Category: Electronics
Quantity: 5

Product 3
SKU: PRN-3001
Thermal Label Printer
Warehouse Equipment
Quantity: 2
"""
    products = parse_products(text_products, text_products.splitlines())
    assert len(products) == 3
    assert products[0].sku == "SCN-1001"
    assert products[0].product_name == "Wireless Barcode Scanner"
    assert products[0].category == "Electronics"
    
    assert products[1].sku == "RFID-2001"
    assert products[1].product_name == "RFID Reader"
    assert products[1].category == "Electronics"
    
    assert products[2].sku == "PRN-3001"
    assert products[2].product_name == "Thermal Label Printer"
    assert products[2].category == "Warehouse Equipment"

    # 5. Stop keyword truncation
    text_party_truncate = """
Supplier Name: ABC Electronics Private Limited Supplier ID: SUP-001 GSTIN: 29ABCDE1234F1Z5
Buyer Name: Main Warehouse Warehouse Code: WH-001 Delivery Zone: North Zone
"""
    party_trunc = _extract_party_info(text_party_truncate)
    assert party_trunc.supplier_name == "ABC Electronics Private Limited"
    assert party_trunc.buyer_name == "Main Warehouse"

    # 6. Blacklisted product names check
    text_blacklisted = """
Product 1
SKU: PRN-3001
SUMMARY
Warehouse Equipment
Quantity: 2
"""
    products_black = parse_products(text_blacklisted, text_blacklisted.splitlines())
    assert len(products_black) == 1
    assert products_black[0].product_name != "SUMMARY"
    assert products_black[0].product_name == "Warehouse Equipment"


def test_extraction_confidence():
    from app.schemas import ExtractedData, DocumentInfo, PartyInfo, FinancialInfo, ProductItem, Dimensions, Weight, ShipmentInfo
    from app.services.classifier import calculate_extraction_confidence

    # Case 1: Minimum populated data
    data = ExtractedData()
    score = calculate_extraction_confidence(data, "invoice", 0.28)
    # required_score = 0/4 = 0.0
    # financial_score = 0/3 = 0.0
    # product_score = 0.0 (empty products list and doc_type is "invoice")
    # classification_score = 0.28
    # bonus = 0.0
    # total = 0.0*0.40 + 0.0*0.25 + 0.0*0.25 + 0.28*0.10 + 0.0 = 0.028 -> round to 0.03
    assert score == 0.03

    # Case 2: Highly populated invoice (nearly perfect)
    data_full = ExtractedData(
        document_info=DocumentInfo(
            invoice_number="INV-2026-1001",
            document_date="2026-06-17",
        ),
        party_info=PartyInfo(
            supplier_name="ABC Electronics Private Limited",
            buyer_name="Main Warehouse",
        ),
        financial_info=FinancialInfo(
            subtotal="5000000",
            tax="900000",
            total_amount="5900000",
        ),
        products=[
            ProductItem(
                sku="SCN-1001",
                product_name="Wireless Barcode Scanner",
                quantity=10,
                dimensions=Dimensions(length=25.0, width=12.0, height=8.0),
                weight=Weight(value=1.2),
            )
        ]
    )
    score_full = calculate_extraction_confidence(data_full, "invoice", 0.28)
    # required_score = 4/4 = 1.0 (invoice_number, document_date, supplier_name, buyer_name all populated)
    # financial_score = 3/3 = 1.0 (subtotal, tax, total_amount populated)
    # product_score = 1.0 (sku, product_name, quantity, dimensions, weight all populated)
    # classification_score = 0.28
    # bonus = 0.0
    # total = 1.0*0.40 + 1.0*0.25 + 1.0*0.25 + 0.28*0.10 = 0.40 + 0.25 + 0.25 + 0.028 = 0.928 -> round to 0.93
    assert score_full == 0.93

    # Case 3: Fully populated invoice + all bonus fields
    data_bonus = ExtractedData(
        document_info=DocumentInfo(
            invoice_number="INV-2026-1001",
            document_date="2026-06-17",
            grn_number="GRN-9999",
        ),
        party_info=PartyInfo(
            supplier_name="ABC Electronics Private Limited",
            buyer_name="Main Warehouse",
        ),
        financial_info=FinancialInfo(
            subtotal="5000000",
            tax="900000",
            total_amount="5900000",
        ),
        shipment_info=ShipmentInfo(
            vehicle_number="KA-01-AB-1234",
            transporter_name="BlueDart Express",
            shipment_id="SH-8888",
            carrier_name="DHL",
            delivery_date="2026-06-18",
        ),
        products=[
            ProductItem(
                sku="SCN-1001",
                product_name="Wireless Barcode Scanner",
                quantity=10,
                dimensions=Dimensions(length=25.0, width=12.0, height=8.0),
                weight=Weight(value=1.2),
            )
        ]
    )
    score_bonus = calculate_extraction_confidence(data_bonus, "invoice", 0.28)
    # 6 bonus fields are present (vehicle_number, transporter_name, shipment_id, grn_number, carrier_name, delivery_date)
    # bonus = 6 * 0.02 = 0.12
    # total before cap = 0.928 + 0.12 = 1.048 -> capped at 1.00
    assert score_bonus == 1.00



