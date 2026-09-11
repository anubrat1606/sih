"""Deterministic extraction: grammars, structural checks, and bounding boxes.

The whole path exercised here runs with no model involved. That is the charter's
tell-tale test made concrete.
"""
import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db
from satyapramana_store.extract import (
    find_candidates, find_pan_holder_fields, gstin_check_digit, pan_from_gstin,
    read_pdf, validate_cin, validate_gstin, validate_pan,
    validate_pan_date_of_birth, validate_pan_holder_name, validate_udyam,
)

from .conftest_pdf import imageless_pdf, pan_card_lines, text_pdf, valid_cin, valid_gstin

GSTIN = valid_gstin()
PAN = pan_from_gstin(GSTIN)
UDYAM = "UDYAM-TN-01-0001234"
CIN = valid_cin()


@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def upload(client, data, bidder="A", tender="T1", name="fixture.pdf"):
    client.post(f"/tenders/{tender}/bidders", json={"bidder_id": bidder})
    return client.post(f"/bidders/{bidder}/documents", params={"tender_id": tender},
                       files={"file": (name, data, "application/pdf")})


# --- grammars and structural checks -------------------------------------------

def test_a_well_formed_gstin_validates():
    check = validate_gstin(GSTIN)
    assert check.ok and "embedded PAN" in check.detail


def test_the_check_digit_catches_a_single_character_slip():
    """An OCR misread still matches the regex. Without this the system would ask
    an authority about a business that does not exist and record the NOT_FOUND
    as if it meant something."""
    broken = GSTIN[:9] + ("1" if GSTIN[9] == "0" else "0") + GSTIN[10:]
    assert not validate_gstin(broken).ok


@pytest.mark.parametrize("bad,why", [
    ("96AAAAA0000A1Z0", "state code"),
    ("33AAAAA0000A1Y0", "grammar"),
    ("33AAAAA0000A1Z", "grammar"),
    ("", "grammar"),
])
def test_malformed_gstins_are_rejected(bad, why):
    assert not validate_gstin(bad).ok


def test_the_pan_holder_type_is_checked():
    assert validate_pan("AAAPA0000A").ok          # P: individual
    assert not validate_pan("AAAXA0000A").ok      # X: not a holder type


def test_udyam_grammar():
    assert validate_udyam(UDYAM).ok
    assert not validate_udyam("UDYAM-TN-1-0001234").ok


def test_a_well_formed_cin_validates():
    check = validate_cin(CIN)
    assert check.ok
    assert "incorporated 2015" in check.detail
    assert "Private Limited Company" in check.detail


@pytest.mark.parametrize("bad,why", [
    ("U74999KA2015PTC01234", "one digit short of the grammar"),
    ("X74999KA2015PTC012345", "listing status is not L or U"),
    ("U749991A2015PTC012345", "digit inside the state-code slot"),
    ("U74999ZZ2015PTC012345", "ZZ is not a Registrar-of-Companies state code"),
    ("U74999KA1500PTC012345", "incorporation year predates the range"),
    ("U74999KA2015XYZ012345", "XYZ is not an ownership class"),
    ("", "empty"),
])
def test_malformed_cins_are_rejected(bad, why):
    assert not validate_cin(bad).ok, why


def test_a_well_formed_date_of_birth_validates():
    check = validate_pan_date_of_birth("15/08/1990")
    assert check.ok and "1990" in check.detail


@pytest.mark.parametrize("bad,why", [
    ("1990-08-15", "wrong format (ISO, not DD/MM/YYYY)"),
    ("15-08-1990", "wrong separator"),
    ("31/02/1990", "February has no 31st"),
    ("32/01/1990", "no 32nd day"),
    ("15/13/1990", "no 13th month"),
    ("15/08/90", "two-digit year"),
    ("", "empty"),
])
def test_malformed_dates_of_birth_are_rejected(bad, why):
    assert not validate_pan_date_of_birth(bad).ok, why


def test_a_well_formed_holder_name_validates():
    assert validate_pan_holder_name("RAHUL KUMAR SHARMA").ok
    assert validate_pan_holder_name("A. K. NAIR").ok


@pytest.mark.parametrize("bad,why", [
    ("", "empty"),
    ("15/08/1990", "a date, not a name"),
    ("RAHUL2", "contains a digit"),
    ("x", "single lowercase char -- not how a card prints a name"),
])
def test_malformed_holder_names_are_rejected(bad, why):
    assert not validate_pan_holder_name(bad).ok, why


def test_a_gstin_carries_its_holders_pan():
    """Identifier match beats semantic similarity, always."""
    assert pan_from_gstin(GSTIN) == GSTIN[2:12]


def test_check_digit_round_trips_for_every_position():
    stem = "33AAAAA0000A1Z"
    computed = gstin_check_digit(stem)
    assert validate_gstin(stem + computed).ok
    for wrong in "0123456789Z":
        if wrong != computed:
            assert not validate_gstin(stem + wrong).ok


# --- locating identifiers on the page -----------------------------------------

def test_an_identifier_is_located_with_its_exact_box():
    pdf = text_pdf(["Test fixture, not a certificate.", f"GSTIN: {GSTIN}"])
    candidates, unreadable = find_candidates(read_pdf(pdf))
    assert not unreadable
    gstins = [c for c in candidates if c.field == "gstin"]
    assert len(gstins) == 1
    found = gstins[0]
    assert found.value == GSTIN and found.valid and found.page == 1
    x0, top, x1, bottom = found.region
    assert x1 > x0 and bottom > top, "a real, non-degenerate rectangle"
    assert 0 < x0 < 600 and 0 < top < 850, "inside the page"


def test_the_box_tracks_where_the_text_actually_is():
    """Two identical documents differing only in vertical position must produce
    different boxes -- otherwise the highlight would be decorative."""
    one = text_pdf([f"GSTIN: {GSTIN}"])
    two = text_pdf(["filler"] * 10 + [f"GSTIN: {GSTIN}"])
    a = next(c for c in find_candidates(read_pdf(one))[0] if c.field == "gstin")
    b = next(c for c in find_candidates(read_pdf(two))[0] if c.field == "gstin")
    assert a.region[1] < b.region[1], "further down the page means a larger top"


def test_a_gstin_is_not_also_reported_as_a_pan():
    """A GSTIN contains a PAN. Scanning shortest-first would report the same
    characters twice."""
    pdf = text_pdf([f"GSTIN: {GSTIN}"])
    fields = [c.field for c in find_candidates(read_pdf(pdf))[0] if c.valid]
    assert fields == ["gstin"]


def test_a_standalone_pan_is_found():
    pdf = text_pdf([f"Permanent Account Number: {PAN}"])
    found = [c for c in find_candidates(read_pdf(pdf))[0] if c.valid]
    assert [c.field for c in found] == ["pan_number"]
    assert found[0].value == PAN


def test_identifiers_across_multiple_pages_keep_their_page_numbers():
    pdf = text_pdf([f"GSTIN: {GSTIN}"], pages=3)
    pages = sorted(c.page for c in find_candidates(read_pdf(pdf))[0] if c.valid)
    assert pages == [1, 2, 3]


def test_a_page_with_no_text_layer_is_recorded_not_guessed():
    candidates, unreadable = find_candidates(read_pdf(imageless_pdf()))
    assert candidates == []
    assert len(unreadable) == 1
    assert "no vision provider configured" in unreadable[0]["reason"].lower()


def test_a_structurally_invalid_candidate_is_reported_as_invalid():
    broken = GSTIN[:14] + ("0" if GSTIN[14] != "0" else "1")
    pdf = text_pdf([f"GSTIN: {broken}"])
    found = [c for c in find_candidates(read_pdf(pdf))[0] if c.field == "gstin"]
    assert found and not found[0].valid
    assert "check digit" in found[0].detail


def test_a_cin_is_located_with_its_exact_box():
    pdf = text_pdf(["Test fixture, not a certificate.", f"CIN: {CIN}"])
    candidates, unreadable = find_candidates(read_pdf(pdf))
    assert not unreadable
    cins = [c for c in candidates if c.field == "cin"]
    assert len(cins) == 1
    found = cins[0]
    assert found.value == CIN and found.valid and found.page == 1
    x0, top, x1, bottom = found.region
    assert x1 > x0 and bottom > top, "a real, non-degenerate rectangle"
    assert 0 < x0 < 600 and 0 < top < 850, "inside the page"


def test_a_cin_is_not_also_reported_as_another_identifier():
    """A CIN embeds runs of letters and digits but no PAN, GSTIN or Udyam
    number. Scanning must not harvest its characters twice."""
    pdf = text_pdf([f"CIN: {CIN}"])
    fields = sorted(c.field for c in find_candidates(read_pdf(pdf))[0] if c.valid)
    assert fields == ["cin"]


def test_cins_across_multiple_pages_keep_their_page_numbers():
    pdf = text_pdf([f"CIN: {CIN}"], pages=3)
    pages = sorted(c.page for c in find_candidates(read_pdf(pdf))[0]
                   if c.valid and c.field == "cin")
    assert pages == [1, 2, 3]


def test_a_structurally_invalid_cin_is_reported_as_invalid():
    broken = "U74999KA1500PTC012345"   # incorporation year predates the range
    pdf = text_pdf([f"CIN: {broken}"])
    found = [c for c in find_candidates(read_pdf(pdf))[0] if c.field == "cin"]
    assert found and not found[0].valid
    assert "year" in found[0].detail


def test_gstin_pan_and_cin_are_each_found_independently_on_one_document():
    """A bidder's document packet realistically carries all three on adjacent
    lines. Adding CIN to the front of SCAN_ORDER must not steal or lose a
    character from the others."""
    pdf = text_pdf(["Test fixture, not a certificate.",
                    f"GSTIN: {GSTIN}", f"PAN: {PAN}", f"CIN: {CIN}"])
    found = {c.field: c.value for c in find_candidates(read_pdf(pdf))[0] if c.valid}
    assert found == {"gstin": GSTIN, "pan_number": PAN, "cin": CIN}


def test_a_rejected_cin_does_not_affect_a_valid_gstin_on_the_same_page():
    broken_cin = "U74999KA1500PTC012345"
    pdf = text_pdf([f"GSTIN: {GSTIN}", f"CIN: {broken_cin}"])
    candidates, _ = find_candidates(read_pdf(pdf))
    valid = {c.field: c.value for c in candidates if c.valid}
    invalid = [c for c in candidates if not c.valid]
    assert valid == {"gstin": GSTIN}
    assert len(invalid) == 1
    assert invalid[0].field == "cin" and invalid[0].value == broken_cin


def test_pan_holder_name_and_dob_are_located_with_their_boxes():
    pdf = text_pdf(["Test fixture, not a certificate.", *pan_card_lines()])
    found = {c.field: c for c in find_pan_holder_fields(read_pdf(pdf))}
    assert set(found) == {"pan_holder_name", "pan_date_of_birth"}
    name, dob = found["pan_holder_name"], found["pan_date_of_birth"]
    assert name.valid and name.value == "RAHUL KUMAR SHARMA" and name.page == 1
    assert dob.valid and dob.value == "15/08/1990"
    for field in (name, dob):
        x0, top, x1, bottom = field.region
        assert x1 > x0 and bottom > top, "a real, non-degenerate rectangle"


def test_a_blank_name_field_is_not_read_as_a_guess():
    """Name is the last thing on the page -- no line follows the label -- so
    there is nothing to (mis)read as the name."""
    pdf = text_pdf(["Date of Birth", "15/08/1990", "Name"])
    found = {c.field: c for c in find_pan_holder_fields(read_pdf(pdf))}
    assert not found["pan_holder_name"].valid
    assert "no value line follows" in found["pan_holder_name"].detail
    assert found["pan_date_of_birth"].valid


def test_a_next_line_that_is_itself_a_label_is_not_read_as_a_value():
    """The card left the name blank, so the line under 'Name' is the next
    printed label, 'Date of Birth' -- not a name."""
    pdf = text_pdf(["Name", "Date of Birth", "15/08/1990"])
    found = {c.field: c for c in find_pan_holder_fields(read_pdf(pdf))}
    assert not found["pan_holder_name"].valid
    assert "itself a printed label" in found["pan_holder_name"].detail
    # The date of birth label, found on its own line further down, still
    # reads its own value correctly -- one blank field doesn't take the rest
    # of the document down with it.
    assert found["pan_date_of_birth"].valid
    assert found["pan_date_of_birth"].value == "15/08/1990"


def test_a_malformed_date_of_birth_is_reported_as_invalid_not_guessed():
    pdf = text_pdf(pan_card_lines(dob="1990-08-15"))
    found = [c for c in find_pan_holder_fields(read_pdf(pdf)) if c.field == "pan_date_of_birth"]
    assert found and not found[0].valid
    assert "DD/MM/YYYY" in found[0].detail


def test_no_pan_holder_labels_means_no_candidates_at_all():
    """A document that simply isn't a PAN card -- e.g. a GST certificate --
    must not produce a pan_holder_name/pan_date_of_birth candidate of any
    kind, valid or invalid. Absence of the label is not itself a failure."""
    pdf = text_pdf([f"GSTIN: {GSTIN}"])
    assert find_pan_holder_fields(read_pdf(pdf)) == []


# --- through the API ----------------------------------------------------------

def test_uploading_a_document_extracts_and_records_it(client):
    pdf = text_pdf(["Test fixture, not a certificate.",
                    f"GSTIN: {GSTIN}", f"PAN: {PAN}"])
    body = upload(client, pdf).json()
    assert body["pages"] == 1
    paths = {e["path"] for e in body["extracted"]}
    assert paths == {"bidder.gst.gstin", "bidder.pan.pan_number"}
    for item in body["extracted"]:
        assert len(item["region"]) == 4


def test_the_document_hash_is_recorded(client):
    import hashlib
    pdf = text_pdf([f"GSTIN: {GSTIN}"])
    body = upload(client, pdf).json()
    assert body["document_sha256"] == hashlib.sha256(pdf).hexdigest()


def test_a_rejected_candidate_is_never_asserted_as_a_value(client, conn):
    broken = GSTIN[:14] + ("0" if GSTIN[14] != "0" else "1")
    pdf = text_pdf([f"GSTIN: {broken}"])
    body = upload(client, pdf).json()
    assert body["extracted"] == []
    assert body["rejected"][0]["candidate"] == broken
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events WHERE event_type='FIELD_EXTRACTED'")
        assert cur.fetchone()[0] == 0


def test_a_mismatched_pan_and_gstin_are_flagged_as_one_conflict(client):
    """The two documents are not about the same legal entity, and no amount of
    name similarity changes that."""
    other = "BBBPB1111B"
    pdf = text_pdf([f"GSTIN: {GSTIN}", f"PAN: {other}"])
    body = upload(client, pdf).json()
    cross = body["identifier_cross_check"]
    assert cross["outcome"] == "IDENTIFIER_CONFLICT"
    assert cross["embedded_pan"] == PAN and cross["pan"] == other


def test_a_matching_pan_and_gstin_are_linked(client):
    pdf = text_pdf([f"GSTIN: {GSTIN}", f"PAN: {PAN}"])
    assert upload(client, pdf).json()["identifier_cross_check"]["outcome"] == "LINKED"


def test_the_cross_check_fires_across_two_separate_uploads(client):
    """A bidder's PAN card and GST certificate are realistically two separate
    files. The second, later upload must see the first upload's identifier."""
    first = upload(client, text_pdf([f"PAN: {PAN}"])).json()
    assert first["identifier_cross_check"] is None  # nothing to cross-check yet

    second = upload(client, text_pdf([f"GSTIN: {GSTIN}"])).json()
    cross = second["identifier_cross_check"]
    assert cross is not None
    assert cross["outcome"] == "LINKED"
    assert cross["pan"] == PAN and cross["gstin"] == GSTIN


def test_a_cross_document_conflict_is_flagged_too(client):
    other_pan = "BBBPB1111B"
    upload(client, text_pdf([f"PAN: {other_pan}"]))
    body = upload(client, text_pdf([f"GSTIN: {GSTIN}"])).json()
    cross = body["identifier_cross_check"]
    assert cross["outcome"] == "IDENTIFIER_CONFLICT"
    assert cross["pan"] == other_pan and cross["embedded_pan"] == PAN


def test_the_cross_check_does_not_reach_across_different_bidders(client):
    """Bidder A's PAN must never be cross-checked against bidder B's GSTIN --
    that would compare two different legal entities' documents as if they
    were one bidder's."""
    upload(client, text_pdf([f"PAN: {PAN}"]), bidder="A")
    body = upload(client, text_pdf([f"GSTIN: {GSTIN}"]), bidder="B").json()
    assert body["identifier_cross_check"] is None


def test_uploading_a_document_extracts_a_cin(client):
    pdf = text_pdf(["Certificate of Incorporation (test fixture).", f"CIN: {CIN}"])
    body = upload(client, pdf).json()
    cin = [e for e in body["extracted"] if e["path"] == "bidder.entity.cin"]
    assert len(cin) == 1
    assert cin[0]["value"] == CIN
    assert cin[0]["page"] == 1 and len(cin[0]["region"]) == 4


def test_a_rejected_cin_is_never_asserted_as_a_value(client, conn):
    broken = "U74999KA1500PTC012345"
    pdf = text_pdf([f"CIN: {broken}"])
    body = upload(client, pdf).json()
    assert body["extracted"] == []
    assert body["rejected"][0]["candidate"] == broken
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events WHERE event_type='FIELD_EXTRACTED'")
        assert cur.fetchone()[0] == 0


def test_uploading_a_pan_card_extracts_holder_name_and_dob(client):
    pdf = text_pdf(["Income Tax Department (test fixture).", *pan_card_lines()])
    body = upload(client, pdf).json()
    by_path = {e["path"]: e for e in body["extracted"]}
    assert by_path["bidder.pan.holder_name"]["value"] == "RAHUL KUMAR SHARMA"
    assert by_path["bidder.pan.date_of_birth"]["value"] == "15/08/1990"
    for path in ("bidder.pan.holder_name", "bidder.pan.date_of_birth"):
        assert len(by_path[path]["region"]) == 4


def test_a_pan_card_with_a_blank_name_field_reports_it_as_rejected(client, conn):
    pdf = text_pdf(pan_card_lines(name=None))
    body = upload(client, pdf).json()
    assert "bidder.pan.holder_name" not in {e["path"] for e in body["extracted"]}
    rejected_paths = {r["path"] for r in body["rejected"]}
    assert "bidder.pan.holder_name" in rejected_paths
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM events WHERE event_type='FIELD_EXTRACTED' "
            "AND payload->>'path'='bidder.pan.holder_name'")
        assert cur.fetchone()[0] == 0


def test_a_non_pdf_upload_fails_honestly(client):
    body = upload(client, b"this is not a pdf", name="notes.txt").json()
    assert body["extracted"] == [] and "could not read as PDF" in body["error"]


def test_an_empty_upload_is_refused(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    r = client.post("/bidders/A/documents", params={"tender_id": "T1"},
                    files={"file": ("empty.pdf", b"", "application/pdf")})
    assert r.status_code == 400


# --- the provenance chain now reaches the document ----------------------------

def test_the_trail_reaches_the_source_document_with_page_and_region(client):
    """The demo axiom: click a verdict, land on the exact line of the PDF."""
    pdf = text_pdf(["Test fixture, not a certificate.", f"GSTIN: {GSTIN}"])
    upload(client, pdf)

    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall state a GSTIN.",
         "source": {"page": 14, "region": [72, 470, 523, 494]},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "exists", "subject": {"field": "bidder.gst.gstin"}}}]}
    client.post("/tenders/T1/rule-pack",
                json={"officer_id": "officer_1", "pack": pack})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)

    trail = client.get("/bidders/A/requirements/R1/provenance").json()["trail"]
    kinds = [t["event_type"] for t in trail]
    assert kinds == ["REQUIREMENT_EVALUATED", "EVIDENCE_FUSED",
                     "FIELD_EXTRACTED", "DOCUMENT_INGESTED"]

    extraction = trail[2]["payload"]
    assert extraction["value"] == GSTIN
    assert extraction["page"] == 1
    assert len(extraction["region"]) == 4
    assert trail[3]["payload"]["storage_ref"].endswith(".pdf")


def test_the_trail_reaches_the_source_document_for_a_cin(client):
    """A CIN read off a company document is the input MCA verification needs and
    the claim its answer is fused against -- the trail must reach the PDF line."""
    pdf = text_pdf(["Test fixture, not a certificate.", f"CIN: {CIN}"])
    upload(client, pdf)

    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall state its Corporate Identification Number.",
         "source": {"page": 14, "region": [72, 470, 523, 494]},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "exists", "subject": {"field": "bidder.entity.cin"}}}]}
    client.post("/tenders/T1/rule-pack",
                json={"officer_id": "officer_1", "pack": pack})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)

    trail = client.get("/bidders/A/requirements/R1/provenance").json()["trail"]
    kinds = [t["event_type"] for t in trail]
    assert kinds == ["REQUIREMENT_EVALUATED", "EVIDENCE_FUSED",
                     "FIELD_EXTRACTED", "DOCUMENT_INGESTED"]

    extraction = trail[2]["payload"]
    assert extraction["value"] == CIN
    assert extraction["page"] == 1
    assert len(extraction["region"]) == 4
    assert extraction["path"] == "bidder.entity.cin"


def test_the_trail_reaches_the_source_document_for_the_holder_name(client):
    """This is the field PanStatusAdapter needs as `pan_holder_name` -- the
    trail proves it, like every other extracted field, comes from a real
    line on a real uploaded document."""
    pdf = text_pdf(["Test fixture, not a certificate.", *pan_card_lines()])
    upload(client, pdf)

    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall state the PAN holder's name.",
         "source": {"page": 14, "region": [72, 470, 523, 494]},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "exists", "subject": {"field": "bidder.pan.holder_name"}}}]}
    client.post("/tenders/T1/rule-pack",
                json={"officer_id": "officer_1", "pack": pack})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)

    trail = client.get("/bidders/A/requirements/R1/provenance").json()["trail"]
    kinds = [t["event_type"] for t in trail]
    assert kinds == ["REQUIREMENT_EVALUATED", "EVIDENCE_FUSED",
                     "FIELD_EXTRACTED", "DOCUMENT_INGESTED"]

    extraction = trail[2]["payload"]
    assert extraction["value"] == "RAHUL KUMAR SHARMA"
    assert extraction["path"] == "bidder.pan.holder_name"
    assert len(extraction["region"]) == 4


def test_a_desirable_requirement_can_pass_with_no_model_in_the_path(client):
    """Remove every model from this system and it still produces correct
    verdicts on already-extracted evidence.

    The requirement is `desirable` deliberately: a MANDATORY one resting solely
    on the bidder's own document is Tier C and is capped at PARTIAL by the
    ceiling -- see the next test. Both behaviours are correct, and the
    distinction between them is the anti-fraud property.
    """
    pdf = text_pdf([f"GSTIN: {GSTIN}"])
    upload(client, pdf)
    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder is encouraged to state a GSTIN.",
         "source": {"page": 14}, "obligation": "desirable", "operator": "LEAF",
         "predicate": {"op": "exists", "subject": {"field": "bidder.gst.gstin"}}}]}
    client.post("/tenders/T1/rule-pack",
                json={"officer_id": "officer_1", "pack": pack})
    verdicts = client.post("/bidders/A/evaluate", params={"tender_id": "T1"},
                           json=EVAL).json()["verdicts"]
    assert verdicts["R1"]["verdict"] == "PASS"


def test_but_a_self_declared_pass_is_capped_at_partial(client):
    """An extracted field is the bidder's own document -- Tier C. A mandatory
    requirement resting solely on it can never reach PASS."""
    pdf = text_pdf([f"GSTIN: {GSTIN}"])
    upload(client, pdf)
    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall hold a valid GSTIN.",
         "source": {"page": 14}, "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "matches", "left": {"field": "bidder.gst.gstin"},
                       "pattern": "[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]"}}]}
    client.post("/tenders/T1/rule-pack",
                json={"officer_id": "officer_1", "pack": pack})
    verdicts = client.post("/bidders/A/evaluate", params={"tender_id": "T1"},
                           json=EVAL).json()["verdicts"]
    assert verdicts["R1"]["verdict"] == "PARTIAL"
    assert verdicts["R1"]["reason"] == "SELF_DECLARED_CEILING"


def test_extracted_evidence_is_labelled_a_claim_not_an_authority_answer(client):
    """Calling a value read off the bidder's own document AUTHORITY_ONLY would
    overstate the evidence -- the exact failure this system exists to avoid."""
    pdf = text_pdf([f"GSTIN: {GSTIN}"])
    upload(client, pdf)
    from .test_decide import EVAL, PACK
    pack = {**PACK, "requirements": [
        {"id": "R1", "text": "Bidder shall state a GSTIN.",
         "source": {"page": 14}, "obligation": "desirable", "operator": "LEAF",
         "predicate": {"op": "exists", "subject": {"field": "bidder.gst.gstin"}}}]}
    client.post("/tenders/T1/rule-pack",
                json={"officer_id": "officer_1", "pack": pack})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    trail = client.get("/bidders/A/requirements/R1/provenance").json()["trail"]
    fused = next(t for t in trail if t["event_type"] == "EVIDENCE_FUSED")
    assert fused["payload"]["outcome"] == "CLAIM_ONLY"
