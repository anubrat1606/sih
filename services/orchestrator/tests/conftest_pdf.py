"""Deterministic PDF fixtures for exercising extraction mechanics.

These are NOT documents. They are plain text-layer PDFs generated at test time,
labelled as fixtures in their own body text, used to check that the extractor
finds a grammar match and computes the right bounding box.

No fixture here is or resembles a government certificate, and no identifier in
one is a claim about a real registration -- the numbers are structurally valid
so that the validators can be exercised, and nothing more. Verifying any of them
returns UNKNOWN, because no authority is configured.
"""
from __future__ import annotations

import io

from satyapramana_store.extract import gstin_check_digit


def valid_gstin(stem: str = "33AAAAA0000A1Z") -> str:
    return stem + gstin_check_digit(stem)


def valid_cin(state: str = "KA", year: str = "2015", ownership: str = "PTC") -> str:
    """A structurally valid 21-character CIN for exercising the validator.

    Not a real registration -- the industry code and the registration number are
    filler digits; only the segments the validator checks (state, year,
    ownership class) carry meaning. A CIN has no check digit.
    """
    return f"U74999{state}{year}{ownership}012345"


def pan_card_lines(
    name: str | None = "RAHUL KUMAR SHARMA",
    dob: str | None = "15/08/1990",
) -> list[str]:
    """The 'Name' / 'Date of Birth' label-then-value lines as printed on a
    real PAN card, for composing into a text_pdf() fixture -- e.g.
    text_pdf(["not a certificate", *pan_card_lines()]).

    Not a real card -- a synthetic name and a synthetic date, arranged the
    way the card actually prints them (label on one line, value on the
    next), so the label/value reader has something realistic to exercise.
    Pass None for either to simulate that field being blank on the card.
    """
    result = ["Name"]
    if name is not None:
        result.append(name)
    result.append("Date of Birth")
    if dob is not None:
        result.append(dob)
    return result


def epan_lines(
    pan: str = "AAAPA0000A",
    name: str | None = "RAHUL KUMAR SHARMA",
    father: str | None = "SURESH SHARMA",
    dob: str | None = "15/08/1990",
) -> list[str]:
    """The text layer of an e-PAN whose labels are part of the card artwork:
    no 'Name' / 'Date of Birth' lines at all, only the values in the card's
    fixed order -- PAN, holder's name, father's name, date of birth.

    Not a card -- filler PAN (structurally valid so the anchor validates),
    synthetic names, synthetic date. Pass None to drop a line and simulate a
    layout that does not match.
    """
    return [pan] + [v for v in (name, father, dob) if v is not None]


def gst_certificate_lines(
    issue: str | None = "01/04/2023",
    expiry: str | None = "31/03/2028",
    *, issue_label: str = "Date of Issue", expiry_label: str = "Date of Expiry",
) -> list[str]:
    """The 'Date of Issue' / 'Date of Expiry' label-then-value lines as
    printed on a GST registration certificate, for composing into a
    text_pdf() fixture -- e.g. text_pdf(["not a certificate", *gst_certificate_lines()]).

    Not a real certificate -- synthetic dates, arranged the way the
    document actually prints them (label on one line, value on the next).
    Pass None for either to simulate that field being blank; pass
    issue_label/expiry_label to exercise an alternate wording ("Issued on",
    "Valid until") instead of the default one.
    """
    result = [issue_label]
    if issue is not None:
        result.append(issue)
    result.append(expiry_label)
    if expiry is not None:
        result.append(expiry)
    return result


def gst_claimed_name_lines(
    legal_name: str | None = "SHREE GANESH ENTERPRISES PRIVATE LIMITED",
    trade_name: str | None = "SHREE GANESH TRADERS",
) -> list[str]:
    """The 'Legal Name' / 'Trade Name' label-then-value lines as printed on
    a GST registration certificate, for composing into a text_pdf() fixture
    -- e.g. text_pdf(["not a certificate", *gst_claimed_name_lines()]).

    Not a real certificate -- synthetic business names, arranged the way
    the certificate actually prints them. Pass None for either to simulate
    that field being blank (a real certificate very often has no separate
    trade name).
    """
    result = ["Legal Name"]
    if legal_name is not None:
        result.append(legal_name)
    result.append("Trade Name")
    if trade_name is not None:
        result.append(trade_name)
    return result


def text_pdf(lines: list[str], pages: int = 1) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for _ in range(pages):
        y = 780
        pdf.setFont("Helvetica", 11)
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def imageless_pdf() -> bytes:
    """A page with no text layer at all, standing in for a scan."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.rect(100, 100, 200, 200, fill=0)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
