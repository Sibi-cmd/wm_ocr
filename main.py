from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import io
import fitz
import numpy as np
from paddleocr import PaddleOCR
import uvicorn

from PIL import Image
from langchain_text_splitters import RecursiveCharacterTextSplitter

app = FastAPI()

ocr_model = PaddleOCR(use_textline_orientation=True, lang="en")

class URLPayload(BaseModel):
    url: str
  

@app.post("/extract")
async def extract_text_from_s3(payload: URLPayload):
    try:
        # Download PDF
        response = requests.get(payload.url)
        response.raise_for_status()
        # Open PDF
        pdf_file = io.BytesIO(response.content)
        doc = fitz.open(stream=pdf_file, filetype="pdf")

        content = ""

        for page in doc:

            # Try normal text extraction first
            text = page.get_text()

            # If no text found, use OCR
            if not text.strip():

                # Convert PDF page to image
                pix = page.get_pixmap()

                img_bytes = pix.tobytes("png")

                image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

                # OCR extraction
                ocr_results = ocr_model.ocr(np.array(image), cls=True)
                if ocr_results:
                    text = " ".join(
                        line[1][0]
                        for line in ocr_results[0]
                        if line and len(line) > 1 and line[1][0].strip()
                    )
                else:
                    text = ""

            content += text + " "

        doc.close()

        # Split text
        # text_splitter = RecursiveCharacterTextSplitter(
        #     chunk_size=payload.chuck_size,
        #     chunk_overlap=payload.overlap,
        # )

        # texts = text_splitter.create_documents([content])

        # FIXED: page_content not pageContent
       
        return {
            "result": content
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error downloading file: {e}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {e}"
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)