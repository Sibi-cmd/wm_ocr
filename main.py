import os
import io
import zipfile
import importlib

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_mkldnn"] = "0"
os.environ["FLAGS_use_onednn"] = "0"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import fitz
import numpy as np
import requests
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, UploadFile, File
from paddleocr import PaddleOCR
from PIL import Image
from pydantic import BaseModel

app = FastAPI()

ocr_model = PaddleOCR(
    use_textline_orientation=True,
    lang="en",
    enable_mkldnn=False,
    ocr_version="PP-OCRv4"
)


class URLPayload(BaseModel):
    url: str


def normalize_ocr_result(ocr_results) -> str:
    """Parse PaddleOCR 3.x predict() results.

    In PaddleOCR 3.x the result is a list of dict-like objects with keys:
      - 'rec_texts': list of recognised strings
      - 'rec_scores': list of confidence floats
      - 'dt_polys': list of bounding-box polygons
    We also keep backward-compat with the old 2.x nested-list format.
    """
    if not ocr_results:
        return ""

    texts = []

    try:
        for page_result in ocr_results:
            if not page_result:
                continue

            # --- PaddleOCR 3.x dict-like result ---
            if hasattr(page_result, "rec_texts") or (
                isinstance(page_result, dict) and "rec_texts" in page_result
            ):
                rec_texts = (
                    page_result.get("rec_texts", [])
                    if isinstance(page_result, dict)
                    else getattr(page_result, "rec_texts", [])
                )
                for t in rec_texts:
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
                continue

            # --- Legacy PaddleOCR 2.x nested list ---
            if isinstance(page_result, (list, tuple)):
                for line in page_result:
                    if isinstance(line, dict):
                        text = line.get("text")
                        if text:
                            texts.append(text.strip())
                    elif isinstance(line, (list, tuple)) and len(line) > 1:
                        text_data = line[1]
                        if isinstance(text_data, (list, tuple)) and len(text_data) > 0:
                            text = text_data[0]
                            if isinstance(text, str) and text.strip():
                                texts.append(text.strip())

    except Exception:
        return ""

    return " ".join(texts)


def ocr_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes using PaddleOCR 3.x predict() API."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Use predict() — the new 3.x API (ocr() is deprecated and
    # its compatibility shim can forward unsupported kwargs like 'cls').
    ocr_results = ocr_model.predict(np.array(image))

    return normalize_ocr_result(ocr_results)


def extract_pdf_text(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    result = []

    try:
        for page in doc:
            text = page.get_text().strip()

            if text:
                result.append(text)
            else:
                pix = page.get_pixmap()
                img_bytes = pix.tobytes("png")
                ocr_text = ocr_image_bytes(img_bytes)

                if ocr_text:
                    result.append(ocr_text)

    finally:
        doc.close()

    return "\n\n".join(result).strip()


def looks_like_docx(file_bytes: bytes) -> bool:
    if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
        return False

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            names = set(archive.namelist())
            return "[Content_Types].xml" in names and any(
                name.startswith("word/") for name in names
            )
    except Exception:
        return False


def extract_docx_text(file_bytes: bytes) -> str:
    try:
        docx = importlib.import_module("docx")
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="python-docx missing. Run: pip install python-docx"
        )

    document = docx.Document(io.BytesIO(file_bytes))
    parts = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)

    for table in document.tables:
        for row in table.rows:
            row_text = " ".join(
                cell.text.strip()
                for cell in row.cells
                if cell.text.strip()
            )
            if row_text:
                parts.append(row_text)

    return "\n".join(parts)


def extract_image_text(file_bytes: bytes) -> str:
    return ocr_image_bytes(file_bytes)


def is_html(content_type: str | None) -> bool:
    content_type = (content_type or "").split(";")[0].strip().lower()
    return content_type in ["text/html", "application/xhtml+xml"]


def extract_html_text(html_bytes: bytes) -> str:
    """Extract readable text from an HTML page using BeautifulSoup."""
    soup = BeautifulSoup(html_bytes, "html.parser")

    # Remove non-visible elements
    for tag in soup(["script", "style", "meta", "link", "noscript", "header",
                     "footer", "nav", "aside", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Collapse blank lines / excessive whitespace
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_text_from_bytes(
    file_bytes: bytes,
    filename: str = "",
    content_type: str = "",
) -> str:
    filename = filename.lower()
    content_type = content_type.lower()

    if (
        file_bytes.startswith(b"%PDF-")
        or filename.endswith(".pdf")
        or content_type == "application/pdf"
    ):
        return extract_pdf_text(file_bytes)

    if filename.endswith(".docx") or looks_like_docx(file_bytes):
        return extract_docx_text(file_bytes)

    if content_type.startswith("image/") or filename.endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif")
    ):
        return extract_image_text(file_bytes)

    # Try to detect image by magic bytes (handles missing content-type)
    try:
        Image.open(io.BytesIO(file_bytes)).verify()
        return extract_image_text(file_bytes)
    except Exception:
        pass

    raise HTTPException(
        status_code=400,
        detail="Unsupported file format. Upload PDF, image, or DOCX."
    )


@app.get("/")
def home():
    return {"status": "OCR service running"}


@app.post("/extract")
def extract_from_url(payload: URLPayload):
    try:
        response = requests.get(
            payload.url,
            timeout=30,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if is_html(content_type):
            # Instead of rejecting, extract readable text from the HTML page
            text = extract_html_text(response.content)

            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="This URL returns an HTML page but no readable text could be extracted."
                )

            return {
                "source": payload.url,
                "content_type": content_type,
                "extracted_from": "html",
                "result": text
            }

        text = extract_text_from_bytes(
            response.content,
            filename=payload.url,
            content_type=content_type
        )

        return {
            "source": payload.url,
            "content_type": content_type,
            "result": text
        }

    except HTTPException:
        raise

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Download error: {e}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {e}")


@app.post("/extract/documents")
def extract_from_uploaded_file(file: UploadFile = File(...)):
    try:
        file_bytes = file.file.read()

        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        text = extract_text_from_bytes(
            file_bytes,
            filename=file.filename or "",
            content_type=file.content_type or ""
        )

        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "result": text
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing uploaded file: {e}"
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=False)