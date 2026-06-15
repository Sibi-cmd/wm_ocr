"""Comprehensive test for all warehouse OCR endpoints."""
import requests
import json
import os

BASE = "http://127.0.0.1:8001"
TEST_IMG = "test_invoice.png"

def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# -----------------------------------------------------------------------
# 1. Health check (legacy)
# -----------------------------------------------------------------------
sep("1. Health Check (GET /)")
r = requests.get(f"{BASE}/")
print(f"Status: {r.status_code}")
print(f"Body: {r.json()}")
assert r.status_code == 200

# -----------------------------------------------------------------------
# 2. Single warehouse document extraction
# -----------------------------------------------------------------------
sep("2. Single Document Extraction (POST /api/v1/ocr/extract)")
with open(TEST_IMG, "rb") as f:
    r = requests.post(f"{BASE}/api/v1/ocr/extract", files={"file": (TEST_IMG, f, "image/png")})

data = r.json()
print(f"HTTP: {r.status_code}")
print(f"Status: {data['status']}")
print(f"Document Type: {data['document_type']}")
print(f"Confidence: {data['confidence_score']}")
print(f"OCR Lines: {len(data['ocr_output'])}")
print(f"Products: {len(data['extracted_data']['products'])}")
print(f"Doc Info: {json.dumps(data['extracted_data']['document_info'], indent=2)}")
print(f"Party Info: {json.dumps(data['extracted_data']['party_info'], indent=2)}")
print(f"Financial: {json.dumps(data['extracted_data']['financial_info'], indent=2)}")
print(f"Shipment: {json.dumps(data['extracted_data']['shipment_info'], indent=2)}")
print(f"Warnings: {data['warnings']}")
print(f"Errors: {data['errors']}")
print(f"Storage keys: {list(data['storage_payloads'].keys())}")
assert data["document_type"] == "invoice"

# -----------------------------------------------------------------------
# 3. Batch extraction (2 copies of the same file)
# -----------------------------------------------------------------------
sep("3. Batch Extraction (POST /api/v1/ocr/extract-batch)")
with open(TEST_IMG, "rb") as f1, open(TEST_IMG, "rb") as f2:
    r = requests.post(
        f"{BASE}/api/v1/ocr/extract-batch",
        files=[
            ("files", ("invoice1.png", f1, "image/png")),
            ("files", ("invoice2.png", f2, "image/png")),
        ]
    )

batch = r.json()
print(f"HTTP: {r.status_code}")
print(f"Batch status: {batch['status']}")
print(f"Total: {batch['total_files']}, Processed: {batch['processed_files']}, Failed: {batch['failed_files']}")
for res in batch["results"]:
    print(f"  - {res['file_name']}: {res['status']} ({res['document_type']})")
assert batch["total_files"] == 2
assert batch["processed_files"] == 2

# -----------------------------------------------------------------------
# 4. File validation — wrong type
# -----------------------------------------------------------------------
sep("4. File Validation — Wrong Type (.txt)")
with open("test_invalid.txt", "w") as f:
    f.write("Not a valid document")
with open("test_invalid.txt", "rb") as f:
    r = requests.post(f"{BASE}/api/v1/ocr/extract", files={"file": ("bad.txt", f, "text/plain")})

data = r.json()
print(f"HTTP: {r.status_code}")
print(f"Status: {data['status']}")
print(f"Errors: {data['errors']}")
assert data["status"] == "failed"
assert any(".txt" in e for e in data["errors"])

# -----------------------------------------------------------------------
# 5. Legacy endpoint — still works
# -----------------------------------------------------------------------
sep("5. Legacy Endpoint (POST /extract/documents)")
with open(TEST_IMG, "rb") as f:
    r = requests.post(f"{BASE}/extract/documents", files={"file": (TEST_IMG, f, "image/png")})

print(f"HTTP: {r.status_code}")
legacy = r.json()
print(f"Has 'result' key: {'result' in legacy}")
print(f"Result length: {len(legacy.get('result', ''))}")
assert r.status_code == 200
assert "result" in legacy

# -----------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------
if os.path.exists("test_invalid.txt"):
    os.remove("test_invalid.txt")

sep("ALL TESTS PASSED!")
