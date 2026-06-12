# Warehouse OCR Micro-Service

An OCR micro-service for the **AI-Powered Intelligent Warehouse Management System**. Extracts structured data from warehouse documents (Purchase Orders, Invoices, Packing Lists, Delivery Notes, GRNs, Product Labels) and returns Django-ready JSON payloads.

## Features

- **Document Classification** — automatically detects document type from OCR text
- **Structured Field Extraction** — pulls document numbers, dates, party info, shipment details, financial data
- **Product Row Parsing** — detects tabular product data and extracts SKU, quantities, dimensions, weight
- **Batch Upload** — process multiple documents in a single request
- **Validation Layer** — validates extracted data and returns warnings/errors
- **Django-Ready Payloads** — pre-built payloads for products, inbound receipts, shipments tables
- **Legacy Endpoints Preserved** — original `/extract` and `/extract/documents` still work

## Supported Document Types

| Type | Keywords |
|------|----------|
| Purchase Order | PO Number, Ordered Quantity, Buyer, Supplier |
| Invoice | Tax Invoice, Invoice Number, GST, Total Amount |
| Packing List | Packing List, Package ID, Shipment ID, Carton Dimensions |
| Delivery Note | Delivery Note, Delivery Challan, Vehicle Number, Transporter |
| GRN | Goods Receipt Note, Received Quantity, Damaged Quantity |
| Product Label | Barcode, Serial Number, Batch Number, Manufacturing Date |

## Supported File Types

- PDF (.pdf)
- PNG (.png)
- JPG / JPEG (.jpg, .jpeg)

## Prerequisites

- Python 3.11 (PaddlePaddle does not yet support Python 3.12+)
- A virtual environment (recommended)

## Quickstart (Windows PowerShell)

```powershell
# Create venv with Python 3.11
py -3.11 -m venv .venv
& .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
pip install pymupdf   # if not already installed

# Start the server
python main.py
```

## Quickstart (Unix / macOS)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server starts on **http://127.0.0.1:8001**.

## API Endpoints

### Health Check

```
GET /
```

### Warehouse OCR — Single Document

```
POST /api/v1/ocr/extract
Content-Type: multipart/form-data

file: <your_document.pdf>
```

**Example using curl:**

```bash
curl -X POST "http://127.0.0.1:8001/api/v1/ocr/extract" \
  -F "file=@invoice.pdf"
```

**Response:**

```json
{
  "status": "success",
  "file_name": "invoice.pdf",
  "document_type": "invoice",
  "confidence_score": 0.72,
  "raw_text": "...",
  "ocr_output": ["line1", "line2"],
  "extracted_data": {
    "document_info": { "invoice_number": "INV-2026-001", "document_date": "2026-06-11" },
    "party_info": { "supplier_name": "ABC Corp", "buyer_name": "XYZ Warehouse" },
    "products": [
      {
        "sku": "LAPTOP001",
        "product_name": "Dell Latitude 5450",
        "quantity": 100,
        "dimensions": { "length": 40, "width": 30, "height": 20, "unit": "cm" },
        "weight": { "value": 3.5, "unit": "kg" }
      }
    ],
    "shipment_info": { "vehicle_number": "KA-01-AB-1234" },
    "financial_info": { "total_amount": "150000" },
    "receipt_info": {}
  },
  "storage_mapping": { ... },
  "storage_payloads": { ... },
  "warnings": ["Missing warehouse name."],
  "errors": []
}
```

### Warehouse OCR — Batch Upload

```
POST /api/v1/ocr/extract-batch
Content-Type: multipart/form-data

files: <document1.pdf>
files: <document2.png>
files: <document3.jpg>
```

**Example using curl:**

```bash
curl -X POST "http://127.0.0.1:8001/api/v1/ocr/extract-batch" \
  -F "files=@invoice.pdf" \
  -F "files=@packing_list.pdf" \
  -F "files=@delivery_note.jpg"
```

**Response:**

```json
{
  "status": "success",
  "total_files": 3,
  "processed_files": 2,
  "failed_files": 1,
  "results": [
    { "file_name": "invoice.pdf", "status": "success", "document_type": "invoice", ... },
    { "file_name": "packing_list.pdf", "status": "success", "document_type": "packing_list", ... },
    { "file_name": "delivery_note.jpg", "status": "failed", "errors": ["..."] }
  ]
}
```

### Legacy Endpoints (still working)

```
POST /extract              — Extract from URL (JSON body: {"url": "..."})
POST /extract/documents    — Extract from uploaded file (single file)
```

## Test Steps

1. **Start the server:**
   ```powershell
   python main.py
   ```

2. **Test health check:**
   ```powershell
   curl http://127.0.0.1:8001/
   ```

3. **Test single document extraction:**
   ```powershell
   curl -X POST "http://127.0.0.1:8001/api/v1/ocr/extract" -F "file=@your_invoice.pdf"
   ```

4. **Test batch upload:**
   ```powershell
   curl -X POST "http://127.0.0.1:8001/api/v1/ocr/extract-batch" -F "files=@doc1.pdf" -F "files=@doc2.png"
   ```

5. **Test file validation (wrong type):**
   ```powershell
   curl -X POST "http://127.0.0.1:8001/api/v1/ocr/extract" -F "file=@readme.txt"
   ```

6. **Test legacy endpoint still works:**
   ```powershell
   curl -X POST "http://127.0.0.1:8001/extract/documents" -F "file=@your_document.pdf"
   ```

7. **Interactive API docs:**
   Open http://127.0.0.1:8001/docs in your browser.

## Project Structure

```
wm_ocr/
├── main.py                  # Entry point — mounts routers, keeps legacy endpoints
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── rest.http                # HTTP test requests (VS Code REST Client)
│
├── app/                     # Warehouse OCR application package
│   ├── config.py            # Constants, file limits, keyword maps
│   ├── schemas.py           # Pydantic response/data models
│   │
│   ├── routers/
│   │   └── warehouse.py     # /api/v1/ocr/extract & extract-batch
│   │
│   ├── services/
│   │   ├── ocr_engine.py    # PaddleOCR + PyMuPDF wrapper
│   │   ├── classifier.py    # Document type classification
│   │   ├── field_extractor.py # Warehouse field extraction
│   │   ├── product_parser.py  # Product row parsing
│   │   ├── dimension_parser.py # Dimension & weight parsing
│   │   ├── validator.py     # Data validation
│   │   └── storage_mapper.py  # Django-ready payload builder
│   │
│   └── utils/
│       └── file_utils.py    # File validation helpers
```

## Troubleshooting / Windows Crash Fixes

PaddleOCR on Windows has several known issues that cause silent hard-crashes. The following configurations have been applied:

1. **Large Image Crash (PP-OCRv5 Bug):** Enforced `ocr_version="PP-OCRv4"` which safely handles large images.
2. **MKLDNN Instruction Errors:** Disabled via `enable_mkldnn=False`.
3. **OpenMP DLL Conflicts:** Enforced `os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"`.
4. **Event Loop Blocking:** All OCR endpoints use `def` (not `async def`) to run in thread pool.

## Notes

- On first run PaddleOCR downloads and initialises its models; startup may take time.
- To bypass the model host connectivity check set `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`.
- Max file size: 20 MB per file.
- Max batch size: 10 files per request.
