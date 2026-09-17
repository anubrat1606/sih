"""Financial-statement extraction: turnover and net worth, read from a
table, normalized to INR paise using the statement's own stated unit.

No fixture here is or resembles a real filed financial statement -- the
figures are structurally plausible table data, arranged the way a real
Schedule III statement prints them, used to exercise the extractor and
nothing more, same convention as conftest_pdf.py's other fixtures.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db
from satyapramana_store.extract.financials import (
    _detect_unit, _parse_amount, find_financial_fields,
)

from .conftest import auth_headers

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def table_pdf(rows: list[list[str]], unit_statement: str | None = "All figures are in Rupees Lakhs",
             second_table: list[list[str]] | None = None) -> bytes:
    """A real bordered table pdfplumber's find_tables() can detect --
    reportlab's Table flowable draws actual vector grid lines, the same
    thing a genuine statement's table has. Not a real statement -- filler
    figures, arranged the way one is laid out, so the table-reading logic
    has something realistic to exercise."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    style = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])
    elems = []
    if unit_statement:
        elems.append(Paragraph(unit_statement, styles["Normal"]))
        elems.append(Spacer(1, 12))
    t = Table(rows)
    t.setStyle(style)
    elems.append(t)
    if second_table:
        elems.append(Spacer(1, 24))
        t2 = Table(second_table)
        t2.setStyle(style)
        elems.append(t2)
    doc.build(elems)
    return buf.getvalue()


TURNOVER_TABLE = [
    ["Particulars", "FY 2024-25", "FY 2023-24"],
    ["Revenue from Operations", "12,34,56,789", "10,00,00,000"],
]
NET_WORTH_TABLE = [
    ["Particulars", "FY 2024-25", "FY 2023-24"],
    ["Net Worth", "5,00,00,000", "4,00,00,000"],
]


# --- pure functions: unit detection and amount parsing ----------------------

def test_detects_lakhs_from_a_realistic_unit_statement():
    assert _detect_unit("All figures are in Rupees Lakhs") == (100_000, "lakh")


def test_detects_crore_even_when_rupees_is_also_present():
    """'in Rupees Crore' names both the currency and the scale -- the scale
    word must win, not whichever word happens to come first."""
    assert _detect_unit("(Rs. in Crore)") == (10_000_000, "crore")
    assert _detect_unit("Amounts stated in Rupees Crore") == (10_000_000, "crore")


def test_detects_bare_rupees_when_no_scale_word_is_present():
    assert _detect_unit("All figures stated in INR") == (1, "rupees")
    assert _detect_unit("Amount in ₹") == (1, "rupees")


def test_unit_is_undetermined_when_nothing_matches():
    assert _detect_unit("Statement of Profit and Loss for the year ended 31 March 2025") is None


def test_parses_a_comma_separated_amount():
    assert _parse_amount("12,34,56,789") == 123456789


def test_parses_a_parenthesized_amount_as_negative():
    assert _parse_amount("(5,00,000)") == -500000


def test_parses_an_amount_with_a_currency_symbol():
    assert _parse_amount("₹ 50,000") == 50000


def test_a_blank_or_dash_cell_is_not_an_amount():
    assert _parse_amount("") is None
    assert _parse_amount("-") is None
    assert _parse_amount(None) is None


def test_non_numeric_text_is_not_an_amount():
    assert _parse_amount("N/A") is None


# --- find_financial_fields: correct extraction -------------------------------

def test_extracts_turnover_normalized_to_paise_with_its_financial_year():
    pdf = table_pdf(TURNOVER_TABLE)
    candidates = find_financial_fields(pdf)
    by_field = {c.field: c for c in candidates}
    turnover = by_field["turnover"]
    assert turnover.valid
    # 12,34,56,789 lakhs -> rupees -> paise
    assert turnover.value == 123456789 * 100_000 * 100
    assert turnover.page == 1
    assert turnover.region != (0.0, 0.0, 0.0, 0.0)
    year = by_field["turnover_financial_year"]
    assert year.valid and "2024" in year.value


def test_extracts_net_worth_normalized_to_paise():
    pdf = table_pdf(NET_WORTH_TABLE)
    candidates = find_financial_fields(pdf)
    by_field = {c.field: c for c in candidates}
    net_worth = by_field["net_worth"]
    assert net_worth.valid
    assert net_worth.value == 50000000 * 100_000 * 100


def test_the_financial_year_candidates_region_points_at_its_own_cell_not_row_zero():
    """A statement's header can sit below an extra title row -- the year
    Candidate's region must cite the row the year was actually read from
    (row 1), not an assumed row-0 header position. Checked against the
    real, independently-read bbox of row 1's own cell, not just "some row
    above the value" -- row 0's cell would satisfy that too, which is
    exactly the bug this guards against."""
    import pdfplumber

    rows = [
        ["Statement of Profit and Loss", "", ""],
        ["Particulars", "FY 2024-25", "FY 2023-24"],
        ["Revenue from Operations", "1,00,000", "90,000"],
    ]
    pdf = table_pdf(rows)

    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        table = doc.pages[0].find_tables()[0]
        expected_row0_bbox = tuple(table.rows[0].cells[1])
        expected_row1_bbox = tuple(table.rows[1].cells[1])
    assert expected_row0_bbox != expected_row1_bbox  # the fixture actually exercises this

    candidates = find_financial_fields(pdf)
    by_field = {c.field: c for c in candidates}
    year_region = by_field["turnover_financial_year"].region
    assert year_region == expected_row1_bbox
    assert year_region != expected_row0_bbox


def test_a_label_with_a_footnote_reference_still_matches():
    rows = [
        ["Particulars", "FY 2024-25"],
        ["Revenue from Operations (Note 15)", "1,00,000"],
    ]
    pdf = table_pdf(rows)
    candidates = find_financial_fields(pdf)
    turnover = next(c for c in candidates if c.field == "turnover")
    assert turnover.valid


@pytest.mark.parametrize("label", ["Total Equity", "Shareholders' Funds", "Net Sales", "Total Revenue"])
def test_accepts_known_label_variants(label):
    field = "net_worth" if "Equity" in label or "Funds" in label else "turnover"
    rows = [["Particulars", "FY 2024-25"], [label, "1,00,000"]]
    pdf = table_pdf(rows)
    candidates = find_financial_fields(pdf)
    match = next((c for c in candidates if c.field == field), None)
    assert match is not None and match.valid


def test_turnover_and_net_worth_on_separate_pages_both_extract():
    """A real financial statement's P&L and balance sheet are typically
    separate tables/pages within one document."""
    pdf = table_pdf(TURNOVER_TABLE, second_table=NET_WORTH_TABLE)
    candidates = find_financial_fields(pdf)
    fields = {c.field for c in candidates if c.valid}
    assert {"turnover", "net_worth"} <= fields


# --- honest absence and honest failure ---------------------------------------

def test_a_document_with_no_matching_table_extracts_nothing():
    pdf = table_pdf([["Particulars", "FY 2024-25"], ["Depreciation", "1,00,000"]])
    candidates = find_financial_fields(pdf)
    assert candidates == []


def test_an_undetermined_unit_is_an_honest_failure_not_a_guess():
    pdf = table_pdf(TURNOVER_TABLE, unit_statement=None)
    candidates = find_financial_fields(pdf)
    turnover = next(c for c in candidates if c.field == "turnover")
    assert not turnover.valid
    assert "unit" in turnover.detail


def test_a_non_numeric_value_cell_is_an_honest_failure():
    rows = [["Particulars", "FY 2024-25"], ["Revenue from Operations", "N/A"]]
    pdf = table_pdf(rows)
    candidates = find_financial_fields(pdf)
    turnover = next(c for c in candidates if c.field == "turnover")
    assert not turnover.valid
    assert "does not read as a number" in turnover.detail


# --- through the real API: proves the paise convention actually round-trips -

@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        c.headers.update(auth_headers(conn, username="fixture_senior"))
        yield c
    app.dependency_overrides.clear()


def upload(client, data, bidder="A", tender="T1", name="statement.pdf"):
    client.post(f"/tenders/{tender}/bidders", json={"bidder_id": bidder})
    return client.post(f"/bidders/{bidder}/documents", params={"tender_id": tender},
                       files={"file": (name, data, "application/pdf")})


def test_a_real_document_upload_extracts_turnover_via_the_api(client):
    pdf = table_pdf(TURNOVER_TABLE)
    body = upload(client, pdf).json()
    extracted = {e["path"]: e for e in body["extracted"]}
    assert extracted["bidder.financials.turnover"]["value"] == 123456789 * 100_000 * 100
    assert extracted["bidder.financials.turnover_financial_year"]["value"]


def test_min_turnover_requirement_evaluates_gte_correctly_against_extracted_evidence(client, conn):
    """The single most important proof for this feature: a mandatory
    MIN_TURNOVER requirement's `gte` predicate must actually resolve
    against the extracted, paise-normalized evidence -- not silently fall
    through to UNKNOWN because of a type mismatch between what extraction
    stores and what the predicate evaluator expects a number to look
    like. Capped at PARTIAL either way (self-declared ceiling, no
    authority to verify against) -- the point here is that it resolves at
    all, deterministically, rather than defaulting to UNKNOWN.
    """
    pdf = table_pdf(TURNOVER_TABLE)
    upload(client, pdf)

    from .test_decide import EVAL, PACK
    threshold = 100_000 * 100_000 * 100  # well below the fixture's turnover
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall have annual turnover of at least the stated threshold.",
         "source": {"page": 1}, "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "gte", "left": {"field": "bidder.financials.turnover"},
                       "right": {"literal": threshold}}}]}
    client.post("/tenders/T1/rule-pack", json={"pack": pack}, headers=auth_headers(conn))
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)

    result = client.get("/bidders/A", params={"tender_id": "T1"}).json()
    verdict = next(v for v in result["verdicts"] if v["requirement_id"] == "R1")
    assert verdict["verdict_effective"] == "PARTIAL"
    assert verdict["reason_effective"] == "SELF_DECLARED_CEILING"


def test_the_trail_reaches_the_source_document_for_turnover(client, conn):
    pdf = table_pdf(TURNOVER_TABLE)
    upload(client, pdf)

    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall state its annual turnover.",
         "source": {"page": 1}, "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "exists", "subject": {"field": "bidder.financials.turnover"}}}]}
    client.post("/tenders/T1/rule-pack", json={"pack": pack}, headers=auth_headers(conn))
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)

    trail = client.get("/bidders/A/requirements/R1/provenance").json()["trail"]
    kinds = [t["event_type"] for t in trail]
    assert kinds == ["REQUIREMENT_EVALUATED", "EVIDENCE_FUSED",
                     "FIELD_EXTRACTED", "DOCUMENT_INGESTED"]
    extraction = trail[2]["payload"]
    assert extraction["path"] == "bidder.financials.turnover"
    assert extraction["value"] == 123456789 * 100_000 * 100
    assert extraction["page"] == 1
    assert len(extraction["region"]) == 4
