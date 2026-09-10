"""
Verification service -- SIH26100.

Every check here either calls a real, live external source, or returns
UNVERIFIED with the actual reason it couldn't. There is no sample/sandbox
response anywhere in this file, on purpose -- see the schema note in
/schemas/verification_result.schema.json.

IMPORTANT -- read before running:
This sandbox environment's own network policy blocks outbound calls to
arbitrary government domains (services.gst.gov.in, epfindia.gov.in), so the
GST and EPFO functions below were written but could NOT be live-tested from
here -- curl to both returned no response at all (proxy policy denial, not
information about the sites themselves). Test these from a normal laptop
with open internet before the demo. If the real request shape differs from
what's stubbed below (very possible -- these aren't documented APIs), fix
the request in gst_public_portal_check() / epfo_public_portal_check() using
your browser devtools capture, not by guessing.

Configure via environment variables before running:
  PAN_KYC_PROVIDER_URL   - your chosen provider's real sandbox endpoint
  PAN_KYC_PROVIDER_KEY   - your API key for it
If these aren't set, the PAN check returns UNVERIFIED and says so --
it will not silently skip or fake the result.

Run: uvicorn main:app --port 8002 --reload
"""
import os
from datetime import date, datetime, timezone

import requests
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="SIH26100 Verification Service")

PAN_KYC_PROVIDER_URL = os.environ.get("PAN_KYC_PROVIDER_URL")
PAN_KYC_PROVIDER_KEY = os.environ.get("PAN_KYC_PROVIDER_KEY")

TIMEOUT_SECONDS = 5


class ExtractedFields(BaseModel):
    pan_number: str | None = None
    name: str | None = None
    gstin: str | None = None
    udyam_number: str | None = None
    epfo_number: str | None = None
    date_of_issue: str | None = None
    date_of_expiry: str | None = None


class VerifyRequest(BaseModel):
    bidder_id: str
    document_type: str
    extracted_fields: ExtractedFields
    confidence: dict = {}
    raw_ocr_text: str = ""
    source_s3_key: str = ""


def _check(field, value_extracted, matched_against, status, confidence, details):
    return {
        "field": field,
        "value_extracted": value_extracted or "",
        "matched_against": matched_against,
        "status": status,
        "confidence": confidence,
        "details": details,
    }


def pan_live_kyc_check(pan_number: str) -> dict:
    if not pan_number:
        return _check("pan_number", "", "LIVE_KYC_PROVIDER", "UNVERIFIED", 0.0,
                       "No PAN number was extracted from the document, nothing to verify.")

    if not PAN_KYC_PROVIDER_URL or not PAN_KYC_PROVIDER_KEY:
        return _check("pan_number", pan_number, "LIVE_KYC_PROVIDER", "UNVERIFIED", 0.0,
                       "PAN_KYC_PROVIDER_URL / PAN_KYC_PROVIDER_KEY not configured. "
                       "Sign up for a real provider sandbox key and set these env vars -- "
                       "this check will not run until real credentials are present.")

    try:
        # NOTE: this request shape is a reasonable default, but you MUST
        # confirm it against your chosen provider's actual API reference --
        # auth header name, body field names, and response shape vary by
        # provider. Do not assume this is correct without checking their docs.
        resp = requests.post(
            PAN_KYC_PROVIDER_URL,
            headers={"Authorization": f"Bearer {PAN_KYC_PROVIDER_KEY}"},
            json={"pan": pan_number},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        is_valid = bool(data.get("valid") or data.get("status") == "active")
        return _check(
            "pan_number", pan_number, "LIVE_KYC_PROVIDER",
            "PASS" if is_valid else "FAIL", 0.95 if is_valid else 0.8,
            f"Live provider response: {data}",
        )
    except requests.RequestException as exc:
        return _check("pan_number", pan_number, "LIVE_KYC_PROVIDER", "UNVERIFIED", 0.0,
                       f"Live call failed: {exc}")


def gst_public_portal_check(gstin: str) -> dict:
    if not gstin:
        return _check("gstin", "", "GST_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                       "No GSTIN was extracted from the document, nothing to verify.")

    try:
        # NOTE: this is the page's public URL, not a confirmed API contract.
        # Inspect the real request the search page fires (browser devtools,
        # Network tab, search a real GSTIN) and replace this call with the
        # exact method/headers/body it uses before relying on it.
        resp = requests.get(
            "https://services.gst.gov.in/services/api/search/taxpayerDetails",
            params={"gstin": gstin},
            timeout=TIMEOUT_SECONDS,
        )
        text_lower = resp.text.lower()
        if "captcha" in text_lower:
            return _check("gstin", gstin, "GST_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                           "GST portal requires CAPTCHA verification for this request -- "
                           "not solvable programmatically. Report this field as unverified "
                           "in the demo rather than faking a result.")
        resp.raise_for_status()
        data = resp.json()
        status = str(data.get("status", "")).lower()
        is_active = status in ("active", "valid")
        return _check("gstin", gstin, "GST_PUBLIC_PORTAL",
                       "PASS" if is_active else "FAIL", 0.9 if is_active else 0.7,
                       f"Portal response: {data}")
    except requests.RequestException as exc:
        return _check("gstin", gstin, "GST_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                       f"Live call failed: {exc}")
    except ValueError:
        return _check("gstin", gstin, "GST_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                       "Portal did not return JSON -- likely an HTML/CAPTCHA page. "
                       "Confirm the real request shape from browser devtools.")


def epfo_public_portal_check(epfo_number: str) -> dict:
    if not epfo_number:
        return _check("epfo_number", "", "EPFO_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                       "No EPFO establishment code was extracted -- note the extraction "
                       "service does not yet have a confirmed regex for this field either.")

    try:
        # Same caveat as GST above: confirm the real request shape first.
        resp = requests.get(
            "https://unifiedportal-emp.epfindia.gov.in/publicPortal/no-auth/misReport/home/loadEstSearchHome",
            params={"establishmentCode": epfo_number},
            timeout=TIMEOUT_SECONDS,
        )
        text_lower = resp.text.lower()
        if "captcha" in text_lower:
            return _check("epfo_number", epfo_number, "EPFO_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                           "EPFO portal requires CAPTCHA verification for this request.")
        resp.raise_for_status()
        return _check("epfo_number", epfo_number, "EPFO_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                       "Request succeeded but response parsing isn't implemented yet -- "
                       "confirm the real response shape before trusting this check.")
    except requests.RequestException as exc:
        return _check("epfo_number", epfo_number, "EPFO_PUBLIC_PORTAL", "UNVERIFIED", 0.0,
                       f"Live call failed: {exc}")


def expiry_check(date_of_expiry: str | None) -> dict | None:
    if not date_of_expiry:
        return None
    try:
        expiry = date.fromisoformat(date_of_expiry)
    except ValueError:
        return _check("expiry", date_of_expiry, "LIVE_KYC_PROVIDER", "UNVERIFIED", 0.0,
                       "date_of_expiry could not be parsed as an ISO date.")
    if expiry < date.today():
        return _check("expiry", date_of_expiry, "LIVE_KYC_PROVIDER", "FAIL", 1.0,
                       "Document has expired as of today's date.")
    return _check("expiry", date_of_expiry, "LIVE_KYC_PROVIDER", "PASS", 1.0,
                   "Document is not expired.")


@app.post("/verify")
async def verify(req: VerifyRequest):
    checks = []
    fields = req.extracted_fields

    if fields.pan_number is not None or req.document_type == "PAN":
        checks.append(pan_live_kyc_check(fields.pan_number))
    if fields.gstin is not None or req.document_type == "GST":
        checks.append(gst_public_portal_check(fields.gstin))
    if fields.epfo_number is not None or req.document_type == "EPFO":
        checks.append(epfo_public_portal_check(fields.epfo_number))
    # UDYAM intentionally omitted: no confirmed real public verification URL
    # yet. Do not add a check here until that URL is confirmed real --
    # see the prompt file's BIT 2 notes.

    exp_check = expiry_check(fields.date_of_expiry)
    if exp_check:
        checks.append(exp_check)

    total = len(checks)
    passed = sum(1 for c in checks if c["status"] == "PASS")
    sub_score = round((passed / total) * 100) if total else 0

    return {
        "bidder_id": req.bidder_id,
        "checks": checks,
        "sub_score": sub_score,
    }


@app.get("/health")
async def health():
    configured = bool(PAN_KYC_PROVIDER_URL and PAN_KYC_PROVIDER_KEY)
    return {
        "status": "ok",
        "pan_kyc_provider_configured": configured,
        "time": datetime.now(timezone.utc).isoformat(),
    }
