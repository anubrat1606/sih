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
