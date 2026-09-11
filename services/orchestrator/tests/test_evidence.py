"""The evidence projection's date normalization.

satyapramana.md section 2.2 puts NORMALIZE between EXTRACT and RESOLVE, and
nothing implemented it as a real stage -- extraction correctly stores a date
exactly as printed (DD/MM/YYYY), and the predicate evaluator correctly
expects only ISO-8601. This is the bridge, found by a live end-to-end check
of a real date_after predicate against a real extracted expiry date, which
came back UNKNOWN/EXTRACTION_FAILED instead of the FAIL it should have been.
"""
from __future__ import annotations

from satyapramana_store.evidence import _normalize


def test_ddmmyyyy_normalizes_to_iso():
    assert _normalize("31/03/2028") == "2028-03-31"
    assert _normalize("01/04/2023") == "2023-04-01"


def test_leap_day_normalizes_correctly():
    assert _normalize("29/02/2024") == "2024-02-29"


def test_a_non_date_string_passes_through_unchanged():
    # PAN, GSTIN, CIN, Udyam numbers -- none of them are shaped like
    # DD/MM/YYYY, so none of them should ever be touched by this.
    assert _normalize("AAAAA0000A") == "AAAAA0000A"
    assert _normalize("33AAAAA0000A1Z9") == "33AAAAA0000A1Z9"
    assert _normalize("Active") == "Active"
    assert _normalize("RAHUL KUMAR SHARMA") == "RAHUL KUMAR SHARMA"


def test_a_non_string_value_passes_through_unchanged():
    assert _normalize(42) == 42
    assert _normalize(None) is None
    assert _normalize(["a", "list"]) == ["a", "list"]


def test_an_impossible_calendar_date_passes_through_unchanged_rather_than_raising():
    # Should never actually reach here -- validate_document_date already
    # rejects this before extraction accepts it -- but _normalize must not
    # raise regardless, only ever decline to normalize.
    assert _normalize("31/02/2023") == "31/02/2023"


def test_an_already_iso_value_passes_through_unchanged():
    assert _normalize("2028-03-31") == "2028-03-31"
