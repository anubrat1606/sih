"""The adapter layer: failure taxonomy, redaction, freshness, registry."""
from datetime import date, datetime, timedelta, timezone

import pytest

from satyapramana.verdicts import Channel, Reason, Tier, Verdict
from satyapramana_store.adapters import (
    Basis, Capability, CapabilityManifest, Failure, FailureCode, LawfulBasis,
    NullAdapter, Observation, Registry, Success, UnconfiguredAdapter,
    VerificationRequest, archive, counts_as_covered, failure_to_judgement,
    freshness, redact_body, redact_headers, redact_url,
)
from satyapramana_store.adapters.outcomes import Freshness

NOW = datetime(2026, 9, 10, 4, 10, tzinfo=timezone.utc)
AS_OF = date(2026, 9, 10)

BASIS = LawfulBasis(Basis.TENDER_EVALUATION, "officer_1", "Tender GEM-X evaluation")


def cap(**kw):
    base = dict(capability_id="GST_STATUS", provides=("bidder.gst.status",),
                tier=Tier.A, channel=Channel.AGGREGATOR, as_of_supported=False,
                freshness_days=30)
    base.update(kw)
    return Capability(**base)


def success(**kw):
    base = dict(observations=(Observation("bidder.gst.status", "ACTIVE",
                                          Tier.A, Channel.AGGREGATOR),),
                raw_response_ref="sha256:aa11", observed_at=NOW)
    base.update(kw)
    return Success(**base)


# --- no failure becomes PASS --------------------------------------------------

@pytest.mark.parametrize("code", list(FailureCode))
def test_no_failure_code_ever_yields_pass(code):
    j = failure_to_judgement(Failure(code, "detail"), cap())
    assert j.verdict is not Verdict.PASS


@pytest.mark.parametrize("code", list(FailureCode))
def test_every_failure_is_unknown_by_default(code):
    """A source being down is not evidence against a bidder."""
    j = failure_to_judgement(Failure(code, "detail"), cap())
    assert j.verdict is Verdict.UNKNOWN
    assert j.reason is code.reason


def test_the_one_declared_path_from_not_found_to_fail():
    pan = cap(capability_id="PAN_STATUS", not_found_is_negative=True,
              not_found_justification=(
                  "The PAN allotment register is complete and authoritative for "
                  "the PAN identifier space."))
    j = failure_to_judgement(Failure(FailureCode.NOT_FOUND, "no record"), pan)
    assert j.verdict is Verdict.FAIL
    assert j.reason is Reason.AUTHORITY_CONTRADICTED


def test_not_found_is_negative_requires_a_written_justification():
    with pytest.raises(ValueError, match="never inferred"):
        cap(not_found_is_negative=True)


def test_other_failures_are_unaffected_by_that_declaration():
    pan = cap(not_found_is_negative=True, not_found_justification="x" * 30)
    j = failure_to_judgement(Failure(FailureCode.UNAVAILABLE, "timeout"), pan)
    assert j.verdict is Verdict.UNKNOWN


def test_as_of_unsupported_does_not_substitute_todays_answer():
    j = failure_to_judgement(Failure(FailureCode.AS_OF_UNSUPPORTED, "no history"), cap())
    assert j.verdict is Verdict.UNKNOWN
    assert j.reason is Reason.AS_OF_UNSUPPORTED


# --- lawful basis -------------------------------------------------------------

def test_bidder_consent_requires_a_consent_reference():
    with pytest.raises(ValueError, match="consent_reference"):
        LawfulBasis(Basis.BIDDER_CONSENT, "officer_1", "purpose")


def test_bidder_consent_with_a_reference_is_accepted():
    LawfulBasis(Basis.BIDDER_CONSENT, "officer_1", "purpose",
                consent_reference="consent-2026-0001")


# --- freshness ----------------------------------------------------------------

def test_freshness_is_measured_from_what_the_authority_asserts():
    """We asked this morning; the authority's answer is a fortnight old. Our
    having queried it recently does not make the fact fresh."""
    old = success(source_asserted_at=date(2026, 7, 1))
    assert freshness(old, cap(), AS_OF) == Freshness.EXPIRED
    recent = success(source_asserted_at=date(2026, 9, 8))
    assert freshness(recent, cap(), AS_OF) == Freshness.FRESH


def test_stale_sits_between_fresh_and_expired():
    stale = success(source_asserted_at=AS_OF - timedelta(days=45))
    assert freshness(stale, cap(), AS_OF) == Freshness.STALE


def test_a_stale_verification_does_not_count_as_coverage():
    stale = success(source_asserted_at=AS_OF - timedelta(days=45))
    assert counts_as_covered(stale, cap(), AS_OF) is False
    fresh = success(source_asserted_at=AS_OF)
    assert counts_as_covered(fresh, cap(), AS_OF) is True


def test_only_tier_a_counts_as_coverage():
    fresh = success(source_asserted_at=AS_OF)
    assert counts_as_covered(fresh, cap(tier=Tier.B), AS_OF) is False
    assert counts_as_covered(fresh, cap(tier=Tier.C), AS_OF) is False


# --- redaction ----------------------------------------------------------------

SECRET = "sk_live_9f2b41ca77d0"


def test_secret_headers_are_replaced():
    out = redact_headers({"Authorization": f"Bearer {SECRET}",
                          "X-API-Key": SECRET, "Accept": "application/json"})
    assert SECRET not in str(out)
    assert out["Accept"] == "application/json"


def test_bearer_tokens_in_unlisted_headers_are_stripped():
    out = redact_headers({"X-Custom": f"Bearer {SECRET}"})
    assert SECRET not in str(out)


def test_credentials_in_the_query_string_are_stripped():
    out = redact_url(f"https://api.example.com/gst?gstin=33AAAAA0000A1Z5&api_key={SECRET}")
    assert SECRET not in out
    assert "33AAAAA0000A1Z5" in out, "the actual query must survive"


def test_json_body_secrets_are_stripped_key_wise():
    out = redact_body(f'{{"gstin":"33AAAAA0000A1Z5","client_secret":"{SECRET}"}}')
    assert SECRET not in out and "33AAAAA0000A1Z5" in out


def test_nested_body_secrets_are_stripped():
    out = redact_body(f'{{"auth":{{"token":"{SECRET}"}},"q":[{{"key":"{SECRET}"}}]}}')
    assert SECRET not in out


def test_an_unparseable_body_is_still_archived_but_scrubbed():
    """Unparseable is not a reason to discard evidence."""
    out = redact_body(f"<xml>Bearer {SECRET}</xml>")
    assert out is not None and SECRET not in out


# --- the registry -------------------------------------------------------------

def test_the_real_registry_loads():
    r = Registry.from_file()
    assert len(r.adapters) == 6
    assert set(r.capabilities()) == {
        "PAN_STATUS", "GST_STATUS", "CIN_STATUS", "UDYAM_STATUS"}


def test_missing_integrations_are_registered_null_adapters_not_omissions():
    r = Registry.from_file()
    nulls = [a for a in r.adapters if a.manifest.is_null]
    assert {a.manifest.adapter_id for a in nulls} == {
        "epfo_establishment", "esic_establishment"}
    outcome = nulls[0].verify(VerificationRequest("ANY", {}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.NOT_CAPABLE


def test_no_lawful_source_and_no_credentials_are_different_facts():
    """An officer deserves to be told which. Both resolve to UNKNOWN."""
    r = Registry.from_file()
    unconfigured = r.for_capability("GST_STATUS")[0]
    assert isinstance(unconfigured, UnconfiguredAdapter)
    out = unconfigured.verify(VerificationRequest("GST_STATUS", {}, BASIS))
    assert out.code is FailureCode.UNAUTHORIZED
    assert "awaiting credentials" in out.detail
    assert failure_to_judgement(out, cap()).verdict is Verdict.UNKNOWN


def test_evidence_paths_resolve_to_capabilities():
    r = Registry.from_file()
    assert r.for_path("bidder.gst.status")[1].capability_id == "GST_STATUS"
    assert r.for_path("bidder.astrology.sign") is None


def test_registering_a_real_adapter_replaces_the_placeholder():
    """The plug-in point: configure an aggregator and it takes over the
    capabilities its manifest declares, touching nothing else."""
    r = Registry.from_file()
    assert isinstance(r.for_capability("GST_STATUS")[0], UnconfiguredAdapter)

    class Live:
        manifest = CapabilityManifest(
            adapter_id="gst_status", adapter_version="1.0.0",
            intermediary="Some Aggregator",
            capabilities=(cap(status="LIVE"),))

        def verify(self, request):
            return success()

    r.register(Live())
    adapter, capability = r.for_capability("GST_STATUS")
    assert not isinstance(adapter, UnconfiguredAdapter)
    assert capability.live
    assert len(r.adapters) == 6, "replaced, not appended"


def test_an_aggregator_capability_must_name_its_intermediary():
    with pytest.raises(ValueError, match="intermediary"):
        CapabilityManifest(adapter_id="x", adapter_version="1.0.0",
                           capabilities=(cap(channel=Channel.AGGREGATOR),))


def test_the_coverage_report_states_the_honest_position():
    rows = Registry.from_file().coverage_report()
    assert not any(r["status"] == "LIVE" for r in rows), (
        "no capability is live until an aggregator account exists")
    unavailable = [r for r in rows if r["status"] == "UNAVAILABLE"]
    assert all(r["detail"] for r in unavailable), (
        "an unavailable capability must say why")


# --- archive (needs a database) -----------------------------------------------

def test_credentials_never_reach_the_archive(conn):
    """Redaction happens before the bytes reach storage, never as a display
    filter. Immutable storage means an archive that ever held a live key
    cannot be cleaned up afterwards."""
    digest = archive(
        conn, adapter_id="gst_status", adapter_version="1.0.0",
        capability_id="GST_STATUS", observed_at=NOW, method="POST",
        url=f"https://api.example.com/gst?api_key={SECRET}",
        request_headers={"Authorization": f"Bearer {SECRET}",
                         "Content-Type": "application/json"},
        request_body=f'{{"gstin":"33AAAAA0000A1Z5","client_secret":"{SECRET}"}}',
        response_status=200, response_headers={"Content-Type": "application/json"},
        response_body='{"status":"ACTIVE"}', lawful_basis=BASIS,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT request_url, request_headers::text, request_body, "
                    "response_body FROM raw_responses WHERE content_sha256=%s",
                    (digest,))
        row = cur.fetchone()
    assert SECRET not in " ".join(str(x) for x in row)
    assert "33AAAAA0000A1Z5" in row[0] or "33AAAAA0000A1Z5" in row[2]
    assert row[3] == '{"status":"ACTIVE"}', "the response is stored verbatim"


def test_failures_are_archived_too(conn):
    """A 500 body is the evidence that the authority was down, and it is what
    answers 'why is this UNKNOWN' eighteen months later."""
    digest = archive(
        conn, adapter_id="gst_status", adapter_version="1.0.0",
        capability_id="GST_STATUS", observed_at=NOW, method="GET",
        url="https://api.example.com/gst", request_headers={}, request_body=None,
        response_status=503, response_headers={}, response_body="upstream down",
        lawful_basis=BASIS)
    with conn.cursor() as cur:
        cur.execute("SELECT response_status, response_body FROM raw_responses "
                    "WHERE content_sha256=%s", (digest,))
        assert cur.fetchone() == (503, "upstream down")


def test_the_archive_is_immutable(conn):
    import psycopg
    archive(conn, adapter_id="a", adapter_version="1.0.0", capability_id="C",
            observed_at=NOW, method="GET", url="https://x", request_headers={},
            request_body=None, response_status=200, response_headers={},
            response_body="{}", lawful_basis=BASIS)
    for stmt in ("UPDATE raw_responses SET response_body='forged'",
                 "DELETE FROM raw_responses", "TRUNCATE raw_responses"):
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.cursor() as cur:
                cur.execute(stmt)
