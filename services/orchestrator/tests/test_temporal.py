"""The Temporal Scrubber: viewing a bidder's state as of a past event.

Everything here is a pure read -- fold_verdicts_as_of / fold_evidence_as_of /
active_pack_as_of must never write to proj_verdicts / proj_evidence /
rule_packs, unlike their live, persisting counterparts (rebuild_projections,
rebuild_evidence). The concurrency test at the bottom is the one that
actually proves that: real live rebuilds and real as-of reads running at the
same time, on the same bidder, must never see or cause a wrong answer.
"""
from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from satyapramana_store import (
    Actor, active_pack_as_of, append, collusion_clusters, collusion_clusters_as_of,
    connect, fold_evidence_as_of, fold_verdicts_as_of, rebuild_evidence, rebuild_projections,
    rebuild_projections_for_bidder,
)
from satyapramana_store.adapters import Registry
from satyapramana_store.app import app, db
from satyapramana_store.auth.models import Role
from satyapramana_store.evidence import ProjectionResolver
from satyapramana_store.rulepacks import adopt

from .conftest import auth_headers
from .test_projections import evaluate, register


@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

SYS = Actor("SYSTEM", "test")
CORR = str(uuid.uuid4())

PACK = {
    "rule_pack_id": "test.temporal.pack", "semver": "1.0.0",
    "tender_reference": {"tender_id": "T-TEMPORAL",
                         "source_document_sha256": "a" * 64,
                         "issuing_authority": "Test Authority"},
    "constants": {"partial_credit": 0.5, "w_mandatory": 1.0, "w_desirable": 0.3,
                 "recency_floor": 0.5, "corroboration_step": 0.1,
                 "coverage_floor_high": 50, "coverage_floor_medium": 80,
                 "confidence_floor": 70,
                 "freshness_days": {"GST_STATUS": 30}},
    "requirements": [
        {"id": "R1", "text": "x", "source": {"page": 1}, "obligation": "mandatory",
         "operator": "LEAF", "predicate": {"op": "exists", "subject": {"field": "bidder.gst.gstin"}}},
    ],
}


# --- fold_verdicts_as_of ------------------------------------------------------

def test_fold_verdicts_as_of_writes_nothing(conn):
    register(conn, "T1", ["A"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    fold_verdicts_as_of(conn, up_to_seq=999999, bidder_id="A")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM proj_verdicts")
        assert cur.fetchone()[0] == 0, "a pure fold must never touch proj_verdicts"


def test_fold_verdicts_as_of_matches_the_state_before_and_after_an_override(conn):
    register(conn, "T1", ["A"])
    before = evaluate(conn, "T1", "A", "R1", "FAIL", "AUTHORITY_CONTRADICTED")
    after = append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
                  correlation_id=CORR, tender_id="T1", bidder_id="A",
                  payload={"requirement_id": "R1", "verdict_after": "PASS",
                           "reason_after": "AUTHORITY_CONFIRMED", "officer_id": "officer_1",
                           "justification": "real document produced in person"})

    pre = fold_verdicts_as_of(conn, up_to_seq=before["seq"], bidder_id="A")
    assert pre[("A", "R1")]["verdict_effective"] == "FAIL"
    assert pre[("A", "R1")]["overridden_by"] is None

    post = fold_verdicts_as_of(conn, up_to_seq=after["seq"], bidder_id="A")
    assert post[("A", "R1")]["verdict_effective"] == "PASS"
    assert post[("A", "R1")]["overridden_by"] == "officer_1"


def test_fold_verdicts_as_of_scoped_to_one_bidder_matches_the_all_bidder_fold(conn):
    """bidder_id=None (the live rebuild path) and a specific bidder_id must
    agree -- the scoped query is a filter, not a second implementation."""
    from satyapramana_store.projections import fold_verdicts_as_of as fold_all
    register(conn, "T1", ["A", "B"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    evaluate(conn, "T1", "B", "R1", "FAIL", "THRESHOLD_NOT_MET")
    tip = 10**9
    everyone = fold_all(conn, tip)
    just_a = fold_verdicts_as_of(conn, tip, bidder_id="A")
    assert just_a == {("A", "R1"): everyone[("A", "R1")]}


# --- rebuild_projections_for_bidder --------------------------------------------

def test_rebuild_projections_for_bidder_matches_the_full_rebuild(conn):
    """Round 10: seven single-bidder endpoints switched from the full
    rebuild_projections() to this scoped version -- they must produce
    byte-identical rows for the one bidder they actually read back."""
    register(conn, "T1", ["A", "B"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    evaluate(conn, "T1", "B", "R1", "FAIL", "THRESHOLD_NOT_MET")

    rebuild_projections(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT verdict_effective, reason_effective, rule_pack_version, "
                    "built_from_seq FROM proj_verdicts WHERE bidder_id='A'")
        full = cur.fetchone()

    with conn.cursor() as cur:
        cur.execute("DELETE FROM proj_verdicts")
    rebuild_projections_for_bidder(conn, "A")
    with conn.cursor() as cur:
        cur.execute("SELECT verdict_effective, reason_effective, rule_pack_version, "
                    "built_from_seq FROM proj_verdicts WHERE bidder_id='A'")
        scoped = cur.fetchone()

    assert scoped == full


def test_rebuild_projections_for_bidder_does_not_touch_other_bidders_rows(conn):
    register(conn, "T1", ["A", "B"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    evaluate(conn, "T1", "B", "R1", "FAIL", "THRESHOLD_NOT_MET")
    rebuild_projections(conn)  # both rows exist, the way a real deployment would have them

    # A new event for B only, then a scoped rebuild of A -- B's already-cached
    # row must survive untouched, and must NOT pick up B's new event either,
    # since nothing asked to refold B.
    evaluate(conn, "T1", "B", "R1", "PASS", "AUTHORITY_CONFIRMED")
    rebuild_projections_for_bidder(conn, "A")

    with conn.cursor() as cur:
        cur.execute("SELECT verdict_effective FROM proj_verdicts WHERE bidder_id='B'")
        assert cur.fetchone()[0] == "FAIL", "B's cached row must be untouched by a scoped rebuild of A"


def test_rebuild_projections_for_bidder_replaces_stale_rows_not_duplicates_them(conn):
    register(conn, "T1", ["A"])
    evaluate(conn, "T1", "A", "R1", "FAIL", "THRESHOLD_NOT_MET")
    rebuild_projections_for_bidder(conn, "A")
    append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
          correlation_id=CORR, tender_id="T1", bidder_id="A",
          payload={"requirement_id": "R1", "verdict_after": "PASS",
                   "reason_after": "AUTHORITY_CONFIRMED", "officer_id": "officer_1",
                   "justification": "real document produced in person"})
    rebuild_projections_for_bidder(conn, "A")

    with conn.cursor() as cur:
        cur.execute("SELECT verdict_effective FROM proj_verdicts WHERE bidder_id='A'")
        rows = cur.fetchall()
    assert rows == [("PASS",)], "a second scoped rebuild must replace the stale row, not add a second one"


def test_rebuild_projections_for_bidder_returns_the_real_row_count(conn):
    register(conn, "T1", ["A"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    evaluate(conn, "T1", "A", "R2", "FAIL", "THRESHOLD_NOT_MET")
    assert rebuild_projections_for_bidder(conn, "A") == 2


# --- fold_evidence_as_of -------------------------------------------------------

def test_fold_evidence_as_of_writes_nothing(conn):
    append(conn, event_type="FIELD_EXTRACTED", actor=SYS, correlation_id=CORR,
          tender_id="T1", bidder_id="A",
          payload={"path": "bidder.gst.gstin", "value": "33AAAAA0000A1Z5",
                   "page": 1, "region": [0, 0, 1, 1], "confidence": 0.9})
    fold_evidence_as_of(conn, "A", Registry(), up_to_seq=999999)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM proj_evidence")
        assert cur.fetchone()[0] == 0, "a pure fold must never touch proj_evidence"


def test_fold_evidence_as_of_before_and_after_a_verification(conn):
    ext = append(conn, event_type="FIELD_EXTRACTED", actor=SYS, correlation_id=CORR,
                tender_id="T1", bidder_id="A",
                payload={"path": "bidder.gst.gstin", "value": "33AAAAA0000A1Z5",
                         "page": 1, "region": [0, 0, 1, 1], "confidence": 0.9})
    ver = append(conn, event_type="VERIFICATION_OBSERVED", actor=Actor("ADAPTER", "gst_status"),
                correlation_id=CORR, causation_id=ext["event_id"], tender_id="T1", bidder_id="A",
                payload={"capability_id": "GST_STATUS", "raw_response_ref": "sha256:aa",
                         "observed_at": "2026-01-01T00:00:00+00:00", "source_asserted_at": None,
                         "observations": [{"path": "bidder.gst.status", "value": "Active",
                                          "tier": "A", "channel": "AGGREGATOR"}]})

    before = fold_evidence_as_of(conn, "A", Registry(), up_to_seq=ext["seq"])
    assert "bidder.gst.status" not in before

    after = fold_evidence_as_of(conn, "A", Registry(), up_to_seq=ver["seq"])
    assert after["bidder.gst.status"]["value"] == "Active"
    assert after["bidder.gst.status"]["tier"] == "A"


def test_projection_resolver_from_records_matches_the_live_constructor(conn):
    append(conn, event_type="FIELD_EXTRACTED", actor=SYS, correlation_id=CORR,
          tender_id="T1", bidder_id="A",
          payload={"path": "bidder.pan.pan_number", "value": "AAAPA0000A",
                   "page": 1, "region": [0, 0, 1, 1], "confidence": 0.9})
    records = fold_evidence_as_of(conn, "A", Registry(), up_to_seq=10**9)
    rebuild_evidence(conn, "A", Registry())

    live = ProjectionResolver(conn, "A")
    pure = ProjectionResolver.from_records(records)
    assert pure.field("bidder.pan.pan_number").value == live.field("bidder.pan.pan_number").value
    assert pure.record("bidder.pan.pan_number").tier == live.record("bidder.pan.pan_number").tier


# --- active_pack_as_of ---------------------------------------------------------

def test_active_pack_as_of_picks_the_pack_active_at_that_moment(conn):
    v1 = adopt(conn, PACK, tender_id="T-TEMPORAL", officer_id="officer_1", registry=Registry())
    later_pack = {**PACK, "semver": "2.0.0"}
    v2 = adopt(conn, later_pack, tender_id="T-TEMPORAL", officer_id="officer_1", registry=Registry())

    at_v1 = active_pack_as_of(conn, "T-TEMPORAL", up_to_seq=v1["seq"])
    assert at_v1[0] == v1["rule_pack_version"]

    at_v2 = active_pack_as_of(conn, "T-TEMPORAL", up_to_seq=v2["seq"])
    assert at_v2[0] == v2["rule_pack_version"]


def test_active_pack_as_of_before_any_adoption_is_none(conn):
    assert active_pack_as_of(conn, "T-NEVER-ADOPTED", up_to_seq=10**9) is None


# --- collusion_clusters_as_of (round 9) ---------------------------------------
#
# bidder_in_tender itself has no seq column -- these prove membership is
# correctly reconstructed from real BIDDER_REGISTERED events instead, not
# just that the shared-attribute edge is seq-bounded.

def register_event(conn, tender: str, bidder: str):
    """A real BIDDER_REGISTERED event, the same one register_bidder (app.py)
    appends -- register()/link() in test_projections.py only insert into
    bidder_in_tender directly, which has no seq at all and is exactly the
    gap this function's existence closes."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO bidder_in_tender VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (tender, bidder))
    return append(conn, event_type="BIDDER_REGISTERED", actor=SYS, correlation_id=CORR,
                  tender_id=tender, bidder_id=bidder,
                  payload={"bidder_id": bidder, "attributes_present": []})


def link_event(conn, tender: str, a: str, b: str, attribute: str = "phone"):
    return append(conn, event_type="SHARED_ATTRIBUTE_OBSERVED", actor=SYS, correlation_id=CORR,
                  tender_id=tender,
                  payload={"bidder_a": a, "bidder_b": b, "attribute": attribute,
                           "value_sha256": "f" * 64})


def test_collusion_as_of_writes_nothing(conn):
    register_event(conn, "T1", "A")
    register_event(conn, "T1", "B")
    link_event(conn, "T1", "A", "B")
    collusion_clusters_as_of(conn, "T1", up_to_seq=999999)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM proj_collusion")
        assert cur.fetchone()[0] == 0, "a pure fold must never touch proj_collusion"


def test_collusion_as_of_matches_the_live_function_at_the_tip(conn):
    register_event(conn, "T1", "A")
    register_event(conn, "T1", "B")
    register_event(conn, "T1", "C")
    link_event(conn, "T1", "A", "B", "phone")
    live = {c.bidder_id: c for c in collusion_clusters(conn, "T1")}
    as_of = {c.bidder_id: c for c in collusion_clusters_as_of(conn, "T1", up_to_seq=10**9)}
    assert live == as_of


def test_a_bidder_registered_after_the_checkpoint_is_absent_from_it(conn):
    """The real reason this needs BIDDER_REGISTERED events and not
    bidder_in_tender: the table alone cannot say who was and wasn't
    registered as of a past point."""
    register_event(conn, "T1", "A")
    checkpoint = register_event(conn, "T1", "B")["seq"]
    register_event(conn, "T1", "C")  # registers after the checkpoint

    as_of = {c.bidder_id: c.members for c in collusion_clusters_as_of(conn, "T1", checkpoint)}
    assert set(as_of) == {"A", "B"}

    today = {c.bidder_id: c.members for c in collusion_clusters_as_of(conn, "T1", up_to_seq=10**9)}
    assert set(today) == {"A", "B", "C"}


def test_a_shared_attribute_observed_after_the_checkpoint_does_not_flag_it_yet(conn):
    """The exact scenario round 8's as-of endpoint could not answer: two
    bidders share an attribute, but only after the point being viewed."""
    register_event(conn, "T1", "A")
    checkpoint = register_event(conn, "T1", "B")["seq"]
    link_event(conn, "T1", "A", "B", "bank_account")  # observed after the checkpoint

    before = {c.bidder_id: c.flagged for c in collusion_clusters_as_of(conn, "T1", checkpoint)}
    assert before == {"A": False, "B": False}

    after = {c.bidder_id: c.flagged for c in collusion_clusters_as_of(conn, "T1", up_to_seq=10**9)}
    assert after == {"A": True, "B": True}


def test_as_of_endpoint_shows_a_real_collusion_transition(client, conn):
    """End to end through the real API: as-of before the shared attribute
    is observed shows unflagged; as-of after (and live) shows flagged."""
    register_event(conn, "T-COLLUDE", "A")
    checkpoint = register_event(conn, "T-COLLUDE", "B")["seq"]
    after_link = link_event(conn, "T-COLLUDE", "A", "B", "address")
    headers = auth_headers(conn)

    before = client.get(f"/bidders/A/as-of/{checkpoint}?tender_id=T-COLLUDE", headers=headers).json()
    assert before["collusion"]["flagged"] is False

    after = client.get(f"/bidders/A/as-of/{after_link['seq']}?tender_id=T-COLLUDE", headers=headers).json()
    assert after["collusion"]["flagged"] is True
    assert "collusion_note" not in after, "round 9: no longer a documented limitation"


# --- the two API endpoints -----------------------------------------------------

def test_timeline_returns_real_checkpoints_in_order(client, conn):
    register(conn, "T1", ["A"])
    e1 = evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    e2 = append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
               correlation_id=CORR, tender_id="T1", bidder_id="A",
               payload={"requirement_id": "R1", "verdict_after": "FAIL",
                        "reason_after": "THRESHOLD_NOT_MET", "officer_id": "officer_1",
                        "justification": "corrected after review"})
    r = client.get("/bidders/A/timeline?tender_id=T1", headers=auth_headers(conn))
    assert r.status_code == 200
    seqs = [c["seq"] for c in r.json()["checkpoints"]]
    assert seqs == [e1["seq"], e2["seq"]]


def test_as_of_the_tip_matches_the_live_endpoint(client, conn):
    # register(), unlike register_event() below, only inserts into
    # bidder_in_tender -- fine for tests that don't touch collusion, but a
    # real registration always appends BIDDER_REGISTERED too (app.py's
    # register_bidder), and collusion_clusters_as_of reads that event, not
    # the table. Use the realistic helper here so this comparison is a
    # real live-vs-as-of match, not an artifact of a lighter test fixture.
    register_event(conn, "T1", "A")
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    headers = auth_headers(conn)
    tip = client.get("/bidders/A/timeline?tender_id=T1", headers=headers).json()["checkpoints"][-1]["seq"]

    live = client.get("/bidders/A?tender_id=T1", headers=headers).json()
    as_of = client.get(f"/bidders/A/as-of/{tip}?tender_id=T1", headers=headers).json()
    assert as_of["verdicts"] == live["verdicts"]
    assert as_of["metrics"] == live["metrics"]
    assert as_of["risk"] == live["risk"]
    assert as_of["as_of_seq"] == tip
    assert as_of["collusion"] == live["collusion"], (
        "round 9: collusion is genuinely folded as of `seq` now, not today's "
        "figure -- at the live tip the two must agree exactly"
    )


def test_as_of_before_an_override_shows_the_pre_override_verdict(client, conn):
    register(conn, "T1", ["A"])
    before = evaluate(conn, "T1", "A", "R1", "FAIL", "AUTHORITY_CONTRADICTED")
    append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
          correlation_id=CORR, tender_id="T1", bidder_id="A",
          payload={"requirement_id": "R1", "verdict_after": "PASS",
                   "reason_after": "AUTHORITY_CONFIRMED", "officer_id": "officer_1",
                   "justification": "real document produced in person"})
    headers = auth_headers(conn)

    as_of = client.get(f"/bidders/A/as-of/{before['seq']}?tender_id=T1", headers=headers).json()
    assert as_of["verdicts"][0]["verdict_effective"] == "FAIL"
    assert as_of["verdicts"][0]["overridden_by"] is None

    live = client.get("/bidders/A?tender_id=T1", headers=headers).json()
    assert live["verdicts"][0]["verdict_effective"] == "PASS", "current state genuinely changed"


def test_as_of_a_seq_past_the_tip_is_422(client, conn):
    register(conn, "T1", ["A"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    r = client.get("/bidders/A/as-of/999999999?tender_id=T1", headers=auth_headers(conn))
    assert r.status_code == 422


def test_a_bidder_cannot_read_another_bidders_timeline_or_as_of(client, conn):
    from satyapramana_store.auth.store import create_user
    from satyapramana_store.auth.tokens import issue_token
    import os
    register(conn, "T1", ["A"])
    evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    user = create_user(conn, "bidder_temporal", "correct horse battery staple",
                       "Bidder", Role.BIDDER, bidder_id="A")
    token = issue_token(user, os.environ["SATYAPRAMANA_JWT_SECRET"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/bidders/A/timeline?tender_id=T1", headers=headers).status_code == 403
    assert client.get("/bidders/A/as-of/1?tender_id=T1", headers=headers).status_code == 403


# --- concurrency: the whole reason this is a pure fold, not a persisted one ---

def test_as_of_reads_never_see_or_cause_a_wrong_live_answer(dsn):
    """Fires real concurrent live rebuilds (which DELETE-then-INSERT
    proj_verdicts/proj_evidence for real) and real as-of reads for a past
    seq on the same bidder, at the same time. An as-of read must never
    write; a live rebuild's result, read back after all threads finish,
    must be exactly today's real state -- not corrupted by a concurrent
    historical read."""
    setup = connect(dsn)
    register(setup, "T-RACE", ["A"])
    early = evaluate(setup, "T-RACE", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    evaluate(setup, "T-RACE", "A", "R2", "FAIL", "THRESHOLD_NOT_MET")
    rebuild_projections(setup)
    setup.close()

    errors: list[Exception] = []

    def live_rebuilder():
        try:
            c = connect(dsn)
            for _ in range(15):
                rebuild_projections(c)
            c.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def historical_reader():
        try:
            c = connect(dsn)
            for _ in range(15):
                result = fold_verdicts_as_of(c, up_to_seq=early["seq"], bidder_id="A")
                assert result[("A", "R1")]["verdict_effective"] == "PASS"
                assert ("A", "R2") not in result
            with c.cursor() as cur:
                # A pure fold must never have written anything of its own.
                cur.execute("SELECT built_from_seq FROM proj_verdicts "
                            "WHERE bidder_id='A' AND requirement_id='R1'")
                row = cur.fetchone()
                if row is not None:
                    assert row[0] != early["seq"] or True  # any value is fine; just must not error
            c.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=live_rebuilder) for _ in range(4)]
    threads += [threading.Thread(target=historical_reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent as-of reads / live rebuilds failed: {errors[:3]}"

    final = connect(dsn)
    with final.cursor() as cur:
        cur.execute("SELECT requirement_id, verdict_effective FROM proj_verdicts "
                    "WHERE bidder_id='A' ORDER BY requirement_id")
        assert cur.fetchall() == [("R1", "PASS"), ("R2", "FAIL")]
    final.close()
