"""
Extraction service — SIH26100.

Real OCR only. No sample/placeholder/mock responses anywhere in this file,
on purpose: every field returned either came out of pytesseract reading the
actual uploaded image, or is null with confidence 0 because it didn't.

Run: uvicorn main:app --port 8001 --reload
"""
import os
import re
import uuid
from datetime import datetime, timezone

import pytesseract
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from PIL import Image

app = FastAPI(title="SIH26100 Extraction Service")

UPLOAD_ROOT = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

DOCUMENT_TYPES = {"PAN", "GST", "UDYAM", "EPFO"}

# Confirmed regexes only. EPFO establishment codes are NOT included here on
# purpose -- the format varies by region/office and hasn't been confirmed.
# Do not add one without confirming it against a real EPFO establishment
# code first; a wrong regex silently produces wrong "extracted" data, which
# is worse than returning null.
PATTERNS = {
    "pan_number": re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]{1}"),
    "gstin": re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}"),
    "udyam_number": re.compile(r"UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}"),
}

FIELD_BY_DOCUMENT_TYPE = {
    "PAN": "pan_number",
    "GST": "gstin",
    "UDYAM": "udyam_number",
    "EPFO": "epfo_number",  # no confirmed pattern yet -- always null for now
}


def empty_extracted_fields() -> dict:
    return {
        "pan_number": None,
        "name": None,
        "gstin": None,
        "udyam_number": None,
        "epfo_number": None,
        "date_of_issue": None,
        "date_of_expiry": None,
    }


def extract_name_below_label(raw_text: str, matched_value: str) -> str | None:
    """Best-effort: return the next non-empty OCR line after the line the
    matched identifier appears on. This is a heuristic, not a guarantee --
    real ID layouts vary. Returns None rather than guessing wildly."""
    lines = [ln.strip() for ln in raw_text.splitlines()]
    for i, line in enumerate(lines):
        if matched_value in line:
            for candidate in lines[i + 1:]:
                if candidate:
                    return candidate
            break
    return None


@app.post("/extract")
async def extract(
    bidder_id: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
):
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"document_type must be one of {sorted(DOCUMENT_TYPES)}")

    bidder_dir = os.path.join(UPLOAD_ROOT, bidder_id)
    os.makedirs(bidder_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = os.path.join(bidder_dir, safe_name)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    try:
        image = Image.open(dest_path)
        raw_text = pytesseract.image_to_string(image)
    except Exception as exc:
        # A real failure to read/OCR the file. Report it plainly, do not
        # fall back to a placeholder result.
        raise HTTPException(status_code=422, detail=f"Could not OCR uploaded file: {exc}")

    extracted_fields = empty_extracted_fields()
    confidence = {}

    target_field = FIELD_BY_DOCUMENT_TYPE[document_type]
    pattern = PATTERNS.get(target_field)

    if pattern is not None:
        match = pattern.search(raw_text.upper())
        if match:
            value = match.group(0)
            extracted_fields[target_field] = value
            confidence[target_field] = 0.9
            found_name = extract_name_below_label(raw_text, value)
            if found_name:
                extracted_fields["name"] = found_name
                confidence["name"] = 0.5  # heuristic, deliberately not high
        else:
            confidence[target_field] = 0.0
    else:
        # e.g. EPFO -- no confirmed regex yet. Leave null, be explicit why.
        confidence[target_field] = 0.0

    return {
        "bidder_id": bidder_id,
        "document_type": document_type,
        "extracted_fields": extracted_fields,
        "confidence": confidence,
        "raw_ocr_text": raw_text,
        "source_s3_key": dest_path,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
